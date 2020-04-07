from config.constants import VOICE_RECORDING
import config.load_django
from database.user_models import Participant, Researcher, StudyRelationship
from database.data_access_models import ChunkRegistry, FileProcessLock, FileToProcess
from database.study_models import Study
import os
from libs.file_processing import process_file_chunks_lambda, do_process_user_file_chunks_lambda_handler
from libs.file_processing_utils import reindex_all_files_to_process
from libs.survey_processing import process_survey_timings_file

import argparse
import config.remote_db_env
from libs.s3 import s3_retrieve, check_for_client_key_pair
from multiprocessing.pool import ThreadPool

from config.constants import ALL_DATA_STREAMS

import json

event={'Records': [{ 's3':{ 'object':{ 'key': 'dummy_file_key' } } }]}

download_request = json.dumps({
        'request_username': 'default_admin',
        'request_datetime': datetime.datetime.now().isoformat()
        'reqeust_study_object_id': ,
        'request_datastreams': ALL_DATA_STREAMS,
        'request_patient_ids': []
        })

def process_data_download_request_lambda_handler(event, context):

    request = json_loads(download_request)

    try:
        researcher = Researcher.objects.get(username=download_request['request_username']))
    except Researcher.DoesNotExist():
        return { 'status_code': 403, 'body': 'Researcher does not exist' }

    if not researcher.site_admin:

        study_relation = StudyRelationship.objects.filter(
                study__object_id=download_request['request_study_object_id'],
                researcher=researcher)

        if not study_relation.exists():
            return { 'status_code': 403,
                     'body': 'Could not find relationship between study and researcher not found!' }

        if study_relation_get().relationship not in ALL_RESEARCH_TYPES:
            return { 'status_code': 403,
                     'body': 'Researcher does not have the correct access privileges to download study data' }

    # if we have gotten this far than the requestor has access to the data, so lets start downloading
    out_dir = f"/tmp/data_download_requst/{download_request['request_study_object_id']}"
    os.makedirs(out_dir)

    for patient_id in download_request['request_patient_ids']:
        for data_stream in download_request['request_data_streams']:
            file_count = 0
            for file_s3_key in s3_list_files(S3_BUCKET, f"RAW_DATA/{patient_id}/{data_stream}"):
                print(file_s3_key)



def orig_download_func():
    parser = argparse.ArgumentParser(description="Beiwe chunker tool")

    # run through all of the jobs waiting to be process and chunk them

    parser.add_argument('study_id', help='Study id number (integer greater than 0).',
        type=int)

    parser.add_argument('out_dir', help='Path to directory where data should be written',
        type=str)

    args = parser.parse_args()

    if args.study_id:

        try:
            study = Study.objects.get(id=args.study_id)
        except:
            print(f'Was not able to find study information for study id = {args.study_id}')
            raise

        print(f'found study information for {study.object_id}, downloading all data and writing to {args.out_dir}')

        for pt in study.participants.filter(device_id__isnull=False):

            if pt.patient_id not in ['286vqdjn', '25rlmdr1']:
                continue

            out_dir = os.path.join(args.out_dir, pt.patient_id)
            os.makedirs(out_dir, exist_ok=True)

            print(f'downloading data for {pt.patient_id} into {out_dir}')

            query = {'user_ids':[pt.patient_id]}
            for chunk in ChunkRegistry.get_chunks_time_range(study.pk, **query).all():
                skip = False
                #for dtype in ['accelerometer', 'gps', 'bluetooth', 'reachability', 'wifi']:
                    #if dtype in chunk.chunk_path:
                        #skip = True
                        #break
                if skip:
                    continue
                if 'surveyAnswers' in chunk.chunk_path:
                    out_filename = os.path.join(out_dir, '_'.join([pt.patient_id]+chunk.chunk_path.split('/')[-3:]))
                else:
                    out_filename = os.path.join(out_dir, '_'.join([pt.patient_id]+chunk.chunk_path.split('/')[-2:]))
                if not os.path.exists(out_filename):
                    file_contents = s3_retrieve(chunk.chunk_path, study.object_id, raw_path=True)
                    with open(out_filename, 'wb') as ofd:
                        ofd.write(file_contents)

if __name__ == "__main__":
