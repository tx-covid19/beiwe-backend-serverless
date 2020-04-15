from config.constants import VOICE_RECORDING
import config.load_django
from database.user_models import Participant, Researcher, StudyRelation
from database.data_access_models import ChunkRegistry, FileProcessLock, FileToProcess
from database.study_models import Study
import os
import argparse
import config.remote_db_env
from libs.s3 import s3_retrieve, check_for_client_key_pair, s3_list_files, s3_upload, s3_upload_not_encrypted
import libs.box as box
from multiprocessing.pool import ThreadPool
from config.constants import ALL_DATA_STREAMS, ALL_RESEARCHER_TYPES, REVERSE_UPLOAD_FILE_TYPE_MAPPING

import json
import datetime
import zipfile
from io import BytesIO

event={'Records': [{ 's3':{ 'object':{ 'key': 'dummy_file_key' } } }]}

#download_request = json.dumps({'request_username': 'cameron',
#                    'request_datetime': datetime.datetime.now().isoformat(),
#                    'request_email_address': 'cameron.craddock@gmail.com',
#                    'request_box_directory': 'beiwe_export',
#                    'request_study_object_id': 'kViHtjgZ3dEzIhL876hV1IpR',
#                    'request_datastreams': ['accelerometer', 'app_log', 'bluetooth', 'calls', 'devicemotion',
#                        'gps', 'gyro', 'identifiers', 'image_survey', 'ios_log', 'magnetometer', 'power_state',
#                        'proximity', 'reachability', 'survey_answers', 'survey_timings', 'texts',
#                        'audio_recordings', 'wifi'],
#                    'request_patient_ids': ['1pcbvyfw', '25rlmdr1', '286vqdjn', '2ulkphrb', '332b3bxa', '3onrr6vt',
#                        '3zq4d3ab', '3zyqpp8g', '44ha4mv1', '48j8ix2e', '4mydzypv', '4q9gu3b8', '5h4hye5n', 
#                        '5k8ow8ru', '5xhmbmap', '63uo1uuj', '6ftd5dn6', '6kyw2uwk', '6mkypp1o', '6z6k8qzx', 
#                        '7373cjon', '79bhqg93', '7rrs62s5', '7rvmfimx', '8l17qdhp', '8spjm55e', '9l7wmsc3', 
#                        'ahiqc5j1', 'b2v1pnc3', 'b9jm44nv', 'bqwty7i3', 'bx5wet5j', 'ca27kihh', 'cd24iebo', 
#                        'cjbncgvw', 'cmv8yskt', 'daneytpw', 'eb1vt4a2', 'edgir25v', 'eu33lm3s', 'f2tdu9gn', 
#                        'f5xj78qv', 'faz8lf76', 'g46wfzjn', 'gfs6odg1', 'h4x9qi13', 'hrzjncys', 'hwx9wm5l', 
#                        'jj1do3qt', 'jm1fbyd3', 'jpift5mo', 'k31skfp1', 'lxg6mqg6', 'lytcvu3h', 'mi3pnw3b', 
#                        'n35hfrwn', 'n6z9d2ur', 'n7z4z8iw', 'ng31u6a6', 'o48dlm7l', 'o7g2lmna', 'oaskvmar', 
#                        'oijvf1fo', 'ozxf6hkg', 'peh6g9i5', 'pho7eama', 'q2butblj', 'q3xw8s3e', 'qozylvnz', 
#                        'qw7a5lo4', 'rs5lr8qg', 'rsx9ostg', 's839pdl8', 'sjzl42nz', 't2vl7lyj', 'tbns4g9n', 
#                        'th3sm5do', 'tn9t3u64', 'udw1qygp', 'uqf1xyc5', 'uqqlx1hw', 'ut1p3z91', 'vd2ajjap', 
#                        'x3e41uss', 'x9qjyn1v', 'xod61c6y', 'xxijk2ms', 'y9sv4o48', 'ylvz6dvf', 'ylz1arq4', 
#                        'z3uokfgj', 'z7trat1j'],
#                    'request_number_of_threads': 8}, indent=4)
#
        #'request_patient_ids': ['4mydzypv'],# '286vqdjn', 'sjzl42nz'],
download_request = json.dumps({
        'request_username': 'cameron',
        'request_datetime': datetime.datetime.now().isoformat(),
        'request_study_object_id': 'kViHtjgZ3dEzIhL876hV1IpR',
        'request_datastreams': ALL_DATA_STREAMS,
        'request_patient_ids': ['sjzl42nz'],
        'request_number_of_threads' : 12,
        'request_box_directory': 'beiwe_export'
        })

def download_s3_data(s3_info):
    """ download function to enable multithreading """
  
    exception = []
    file_contents = []
    
    s3_key, study_object_id = s3_info

    try:
        file_contents = s3_retrieve(s3_key, study_object_id, raw_path=True)
    except Exception as e:
        exception = e
    
    return { 's3_key':s3_key, 'file_contents': file_contents, 'exception': exception } 


def process_data_download_request_lambda_handler(event, context):
    """ This will no longer be a lambda, but OK """

    request = json.loads(download_request)

    try:
        study = Study.objects.get(object_id=request['request_study_object_id'])
    except:
        return { 'status_code': 403, 'body': 'Study does not exist' }

    try:
        researcher = Researcher.objects.get(username=request['request_username'])
    except:
        return { 'status_code': 403, 'body': 'Researcher does not exist' }

    if not researcher.site_admin:

        study_relation = StudyRelation.objects.filter(
                study=study,
                researcher=researcher)

        if not study_relation.exists():
            return { 'status_code': 403,
                     'body': 'Could not find relationship between study and researcher not found!' }

        if study_relation.get().relationship not in ALL_RESEARCHER_TYPES:
            return { 'status_code': 403,
                     'body': 'Researcher does not have the correct access privileges to download study data' }

    if not researcher.has_box_integration:
            return { 'status_code': 403,
                     'body': 'Beiwe does not have access to this users box account' }

    # if we have gotten this far than the requestor has access to the data, so lets start downloading
    #number_of_threads = 4
    if 'request_number_of_threads' in request:
        number_of_threads = request['request_number_of_threads']

    pool = ThreadPool(number_of_threads) 

    patient_id_list = request['request_patient_ids']

    for patient_id in patient_id_list:

        output_file_path = f"{request['request_box_directory']}/{researcher.username}_{request['request_datetime']}/{study.object_id}/{patient_id}"
        box_subfolder = box.create_subfolder_path(output_file_path, researcher.box_integration)
        print(f"create {output_file_path}")

        for data_stream in request['request_datastreams']:

            print(f"processing data for {patient_id} {data_stream}")

            if 'identifiers' in data_stream:
                s3_key = f"RAW_DATA/{study.object_id}/{patient_id}/identifiers_"
            else:
                s3_key = f"RAW_DATA/{study.object_id}/{patient_id}/{REVERSE_UPLOAD_FILE_TYPE_MAPPING[data_stream]}"

            file_list = s3_list_files(s3_key)

            num_file = 0
            output_file_number = 0
            while file_list:

                # do stuff in memory to be faster
                zip_file_stream = BytesIO()

                with zipfile.ZipFile(zip_file_stream, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_fd:
                    # lets truncate the zip file around 1.5 GB, this could vary widely based on how much data
                    # one patient has.
                    while zip_file_stream.getbuffer().nbytes < 1.5*2**32:

                        file_name = file_list.pop()

                        data = download_s3_data((file_name, study.object_id))

                        if 'exception' in data and data['exception']:
                            print( "Error downloading {data['s3_key''}" )
                            raise data['exception']

                        else:

                            if 'surveyAnswers' in data['s3_key'] or 'surveyTimings' in data['s3_key']:
                                out_filename = os.path.join(patient_id, '_'.join([patient_id]+data['s3_key'].split('/')[-3:]))
                            else:
                                out_filename = os.path.join(patient_id, '_'.join([patient_id]+data['s3_key'].split('/')[-2:]))

                            # is this safe? do we need locks?
                            zip_fd.writestr(out_filename, data['file_contents'])

                        if num_file % 50 == 0:
                            print(f'completed {num_file}/{len(file_list)}')
                        num_file += 1

                        # check for completion
                        if not file_list:
                            break

                out_filename = f"{data_stream}.zip"
                if output_file_number > 0:
                    out_filename = f"{data_stream}_{output_file_number}.zip"

                response = box.upload_stream_to_subfolder(box_subfolder, zip_file_stream, out_filename)
                output_file_number += 1

                print(f"wrote {response} {zip_file_stream.getbuffer().nbytes} bytes to {output_file_path}/{out_filename}")

    pool.close()

    return { 'status': 200, 'body': 'success' }

if __name__ == "__main__":
    context=None
    ret_val = process_data_download_request_lambda_handler(event, context)
    print(ret_val)
