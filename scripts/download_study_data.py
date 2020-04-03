from config.constants import VOICE_RECORDING
import config.load_django
from database.user_models import Participant
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

if __name__ == "__main__":

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
