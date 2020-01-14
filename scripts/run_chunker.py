from config.constants import VOICE_RECORDING
import config.load_django
from database.user_models import Participant
from database.data_access_models import ChunkRegistry, FileProcessLock, FileToProcess
import os
from libs.file_processing import process_file_chunks_lambda, do_process_user_file_chunks_lambda_handler
from libs.file_processing_utils import reindex_all_files_to_process
import argparse
import config.remote_db_env
from libs.s3 import s3_retrieve, check_for_client_key_pair
from multiprocessing.pool import ThreadPool

def check_and_update_number_of_observations(chunk):

    if chunk.data_type == VOICE_RECORDING:
        chunk.file_size = 1
        chunk.save()
    else:
        file_contents = s3_retrieve(chunk.chunk_path,
                                    study_object_id=chunk.study.object_id,
                                    raw_path=True)

        # we want to make sure that there are no extraneous newline characters at the
        # end of the line. we want the line to end in exactly one newline character
        file_contents = file_contents.rstrip('\n') + '\n'
    
        # we subtract one to exclude the header line
        chunk.file_size = file_contents.count('\n') - 1
        chunk.save()

    print('Updated chunk {0} with {1} observations'.format(chunk, chunk.file_size))

    return

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Beiwe chunker tool")

    # run through all of the jobs waiting to be process and chunk them

    parser.add_argument('--unlock', help='Unlock the fileprocessing lock.',
        action='store_true', default=False)

    parser.add_argument('--reindex', help='Delete all chunked data and entries in ChunkRegistry and FileToProcces tables. Repopulation FileToProcess with raw files from the S3 bucket.',
        action='store_true', default=False)

    parser.add_argument('--process_ftps', help='Chunk all of the data in the FilesToProcess table.',
        action='store_true', default=False)

    parser.add_argument('--set_num_obs', help='Set the number of observations for each chunk',
        action='store_true', default=False)

    parser.add_argument('--run_serially', help='process the files in serial, default is to process in parallel using a threadpool',
        action='store_true', default=False)

    parser.add_argument('--num_to_process', help='Only process the first N chunks, set to 0 to do all (default)',
        type=int, default=0)

    parser.add_argument('--check_creds', help='Chunk all of the data in the FilesToProcess table.',
            action='store', nargs=2, type=str, metavar=('patient_id', 'study_object_id'))

    parser.add_argument('--chunk_path', help='Chunk a file at a specified path, as opposed to going through all files in the FTP table.',
            action='store', type=str, metavar=('s3_path'))

    parser.add_argument('--rechunk', help='If a file has already been chunkend, then it will be set to deleted in the FTP table, if this flag is used, the FTP table will be undeleted so that the data can be rechunked',
        action='store_true', default=False)


    parser.add_argument('--download_chunk', help='Download file from a specified path.',
            action='store', type=str, metavar=('s3_path'))

    args = parser.parse_args()

    if args.unlock is True:
        FileProcessLock.unlock()

    if args.reindex is True:
        reindex_all_files_to_process()

    if args.download_chunk:
        outfile_name = os.path.basename(args.download_chunk)
        study_id = args.download_chunk.split('/')[1]
        print(f'downloding file at {study_id} :: {args.download_chunk} to {outfile_name}')
        file_contents = s3_retrieve(args.download_chunk, study_id, raw_path=True)
        print(type(file_contents))
        print(len(file_contents))
        with open(outfile_name, 'wb') as ofd:
            ofd.write(file_contents)

    if args.chunk_path:

        print(f'processing path {args.chunk_path}')

        if args.rechunk:
            file_path_items = args.chunk_path.split('/')
            user = Participant.objects.get(patient_id=file_path_items[2])
            FileToProcess.append_file_for_processing(args.chunk_path, user.study.object_id, participant=user)

        event={'Records': [{
                    's3':{
                        'object':{
                            'key': args.chunk_path,
                        }
                    }
                }]}


        # Process the desired number of files and calculate the number of unprocessed files
        retval = do_process_user_file_chunks_lambda_handler(event, [])
        print(retval)

        
    if args.check_creds:
        if check_for_client_key_pair(args.check_creds[0], args.check_creds[1]):
            print(f'A key pair for {args.check_creds[1]}::{args.check_creds[0]} exists')
        else:
            print(f'A key pair for {args.check_creds[1]}::{args.check_creds[0]} does not exist')

    if args.process_ftps:
        process_file_chunks_lambda(args.num_to_process)

    if args.set_num_obs:

        pool = None
        if not args.run_serially:
            pool = ThreadPool(8)

        if args.num_to_process > 0:
            chunks_to_fix = ChunkRegistry.objects.filter(number_of_observations=None)[0:args.num_to_process]
        else:
            chunks_to_fix = list(ChunkRegistry.objects.filter(number_of_observations=None))

        if args.run_serially:
            for chunk in chunks_to_fix:
                check_and_update_number_of_observations(chunk)

        else:
            pool.map(check_and_update_number_of_observations, chunks_to_fix)
            pool.close()
            pool.terminate()
