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

download_request = json.dumps({
        'request_username': 'cameron',
        'request_datetime': datetime.datetime.now().isoformat(),
        'request_study_object_id': 'kViHtjgZ3dEzIhL876hV1IpR',
        'request_datastreams': ALL_DATA_STREAMS,
        'request_patient_ids': ['4mydzypv', '286vqdjn', 'sjzl42nz'],
        'request_number_of_threads' : 12,
        'request_box_directory': 'beiwe_export'
        })

def download_s3_data(s3_info):
  
    exception = []
    file_contents = []
    
    s3_key, study_object_id = s3_info

    try:
        file_contents = s3_retrieve(s3_key, study_object_id, raw_path=True)
    except Exception as e:
        exception = e
    
    return { 's3_key':s3_key, 'file_contents': file_contents, 'exception': exception } 

def process_data_download_request_lambda_handler(event, context):

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
    number_of_threads = 4
    if 'request_number_of_threads' in request:
        number_of_threads = request['request_number_of_threads']

    pool = ThreadPool(number_of_threads) 

    output_file_number = 0

    patient_id_list = request['request_patient_ids']

    output_file_path = f"{request['request_box_directory']}/{study.object_id}"

    print(f"create {output_file_path}")

    box_subfolder = box.create_subfolder_path(output_file_path, researcher.box_integration)

    while patient_id_list:

        # do stuff in memory to be faster
        zip_file_stream = BytesIO()

        with zipfile.ZipFile(zip_file_stream, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_fd:

            # lets truncate the zip file around 1.5 GB, this could vary widely based on how much data
            # one patient has.
            while zip_file_stream.getbuffer().nbytes < 1.5*2**30:

                patient_id = patient_id_list.pop()

                file_list = []

                for data_stream in request['request_datastreams']:

                    print(f"processing data for {patient_id} {data_stream}")

                    if 'identifiers' in data_stream:
                        s3_key = f"RAW_DATA/{study.object_id}/{patient_id}/identifiers_"
                    else:
                        s3_key = f"RAW_DATA/{study.object_id}/{patient_id}/{REVERSE_UPLOAD_FILE_TYPE_MAPPING[data_stream]}"

                    file_list += [(file_s3_key, study.object_id) for file_s3_key in (s3_list_files(s3_key))]

                    print(f"identified {len(file_list)} files to download")

                for data in pool.imap_unordered(download_s3_data, file_list, chunksize=1):

                    if 'exception' in data and data['exception']:
                        print( "Error downloading {data['s3_key''}" )
                        raise data['exception']

                    else:

                        if 'surveyAnswers' in data['s3_key'] or 'surveyTimings' in data['s3_key']:
                            out_filename = os.path.join(patient_id, '_'.join([patient_id]+data['s3_key'].split('/')[-3:]))
                        else:
                            out_filename = os.path.join(patient_id, '_'.join([patient_id]+data['s3_key'].split('/')[-2:]))

                        zip_fd.writestr(out_filename, data['file_contents'])

                # check for completion
                if not patient_id_list:
                    break

            out_filename = f"{researcher.username}_{request['request_datetime']}_{output_file_number}.zip"
            response = box.upload_stream_to_subfolder(box_subfolder, zip_file_stream, out_filename)

            print(f"wrote {response} {zip_file_stream.getbuffer().nbytes} bytes to {output_file_path}/{out_filename}")
            # now we create a presigned link


    return { 'status': 200, 'body': 'success' }

if __name__ == "__main__":
    context=None
    ret_val = process_data_download_request_lambda_handler(event, context)
    print(ret_val)
