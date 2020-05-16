from config.constants import VOICE_RECORDING
import config.load_django
from database.user_models import Participant, Researcher, StudyRelation
from database.data_access_models import ChunkRegistry, FileProcessLock, FileToProcess
from database.study_models import Study
import os
import argparse
import config.remote_db_env
from libs.s3 import s3_retrieve, check_for_client_key_pair, s3_list_files, s3_upload
import libs.box as box
from multiprocessing.pool import ThreadPool
from config.constants import (ALL_DATA_STREAMS, ALL_RESEARCHER_TYPES, REVERSE_UPLOAD_FILE_TYPE_MAPPING,
                              PIPELINE_THREADS, API_TIME_FORMAT)

import json
import datetime
import zipfile
from io import BytesIO


def download_s3_data(s3_info):
    """
    method to download object from s3 into memory, designed to be called using the thread pool
    :param s3_info: (s3_key, study_object_id) tuple, s3_key is the path of the object to be downloaded for the study
        indicated bo study_object_id
    :return: a dictionary { 's3_key':s3_key, 'file_contents': file_contents, 'exception': exception }, exception
        contains any exceptions that occurred during the download, and is None if no exception occurred
    """

    exception = None
    file_contents = None

    # decode input arguments
    s3_key, study_object_id = s3_info

    try:
        file_contents = s3_retrieve(s3_key, study_object_id, raw_path=True)
    except Exception as e:
        exception = e

    return {'s3_key': s3_key, 'file_contents': file_contents, 'exception': exception}


def copy_data_to_box(request):
    """
    copy data from s3 to box, data will be written into a the box_directory provided in the request. The output file
    path will correspond to box_directory/request['datetime_string']/patient_id/datastream.zip, output files will be
    truncated at 1.5GB, if more than one file is needed for a datastream, its filename will be appended with the file
    number.

    :param request: dictionary containing the various parameters for the requested operation
         {
            'username': the name of the beiwe user that made the request,
            'datetime': ISO string of the day and time the request was made,
            'study_object_id': object id of the study that the data belongs to,
            'datastreams': data streams to be copied, check config.constants for a list,
            'patient_ids': list of patient_ids for the data that should be downloaded,
            'box_directory': name of the directory that the data should be copied to on box.com
        }
    :return:
    """

    try:
        study = Study.objects.get(object_id=request['study_object_id'])
    except:
        return {'status_code': 403, 'body': 'Study does not exist'}

    try:
        researcher = Researcher.objects.get(username=request['username'])
    except:
        return {'status_code': 403, 'body': 'Researcher does not exist'}

    if not researcher.site_admin:

        study_relation = StudyRelation.objects.filter(
            study=study,
            researcher=researcher)

        if not study_relation.exists():
            return {'status_code': 403,
                    'body': 'Could not find relationship between study and researcher not found!'}

        if study_relation.get().relationship not in ALL_RESEARCHER_TYPES:
            return {'status_code': 403,
                    'body': 'Researcher does not have the correct access privileges to download study data'}

    if not researcher.has_box_integration:
        return {'status_code': 403,
                'body': 'Beiwe does not have access to this users box account'}

    # if we have gotten this far than the requester has access to the data, so lets start downloading
    pool = ThreadPool(PIPELINE_THREADS)

    # if patient ids list is empty, assume we want them all
    if not request['patient_ids']:
        print('A list of participant ids was not found in the request, defaulting to all participants.')
        patient_id_list = study.participants.all().values_list('patient_id', flat=True)
    else:
        patient_id_list = request['patient_ids']

    if not request['datastreams']:
        print('A list of data streams was not found in the request, defaulting to all data streams')
        data_streams = ALL_DATA_STREAMS
    else:
        data_streams = request['datastreams']

    for patient_id in patient_id_list:

        output_file_path = f"{request['box_directory']}/{request['datetime']}/" \
                           f"{study.name.replace(' ','_')}/{patient_id}"
        box_subfolder = box.create_subfolder_path(output_file_path, researcher.box_integration)

        for data_stream in request['datastreams']:

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
                    while zip_file_stream.getbuffer().nbytes < 1.5 * 2 ** 32:

                        file_name = file_list.pop()

                        data = download_s3_data((file_name, study.object_id))

                        if 'exception' in data and data['exception']:
                            return {'status': 404, 'body': f"Error downloading {data['s3_key']}"}
                        else:

                            if 'surveyAnswers' in data['s3_key'] or 'surveyTimings' in data['s3_key']:
                                out_filename = os.path.join(patient_id,
                                                            '_'.join([patient_id] + data['s3_key'].split('/')[-3:]))
                            else:
                                out_filename = os.path.join(patient_id,
                                                            '_'.join([patient_id] + data['s3_key'].split('/')[-2:]))

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

                # exception is caught in the upload_stream_to_subfolder exception and will be returned
                # as response = None, we are just ignoring these issues for now.
                if response:
                    output_file_number += 1

                    print(f"wrote {response} {zip_file_stream.getbuffer().nbytes} bytes to "
                          f"{output_file_path}/{out_filename}")

    pool.close()

    return {'status': 200, 'body': 'success'}
