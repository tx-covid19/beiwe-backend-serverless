import os
import codecs
import gc
import sys
import traceback
from collections import defaultdict, deque
from datetime import datetime
from multiprocessing.pool import ThreadPool
from pprint import pprint
from typing import DefaultDict, Generator, List, Tuple

from cronutils.error_handler import ErrorHandler

# noinspection PyUnresolvedReferences
from config import load_django
from config.settings import IS_SERVERLESS
from config.constants import (ACCELEROMETER, ANDROID_LOG_FILE, API_TIME_FORMAT, CALL_LOG,
    CHUNK_TIMESLICE_QUANTUM, CHUNKABLE_FILES, CHUNKS_FOLDER, CONCURRENT_NETWORK_OPS,
    DATA_PROCESSING_NO_ERROR_STRING, FILE_PROCESS_PAGE_SIZE, IDENTIFIERS, IOS_LOG_FILE,
    SURVEY_DATA_FILES, SURVEY_TIMINGS, UPLOAD_FILE_TYPE_MAPPING, WIFI)
from database.data_access_models import ChunkRegistry, FileProcessLock, FileToProcess
from database.study_models import Survey
from database.user_models import Participant
from libs.s3 import s3_retrieve, s3_upload, check_for_client_key_pair, create_client_key_pair
import json
import logging

from libs.logfile_processing import process_android_log_data
from libs.survey_processing import process_survey_timings_data, resolve_survey_id_from_file_name

logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.INFO)

class OldBotoImportThatNeedsFixingError(Exception): pass
class EverythingWentFine(Exception): pass
class ProcessingOverlapError(Exception): pass

file_processing_func = {
    SURVEY_TIMINGS: process_survey_timings_data,
    ANDROID_LOG_FILE: process_android_log_data,
}

"""########################## Hourly Update Tasks ###########################"""


def process_file_chunks_lambda(count: int):
    """
    This is the function that is called from the command line.  It runs through all new files
    that have been uploaded and 'chunks' them using the lambda handler. Handles logic for skipping 
    bad files, raising errors appropriately.
    This is primarily called manually during testing and debugging.
    """
    # Initialize the process and ensure there is no other process running at the same time
    error_handler = ErrorHandler()
    if FileProcessLock.islocked():
        raise ProcessingOverlapError("Data processing overlapped with a previous data indexing run.")
    FileProcessLock.lock()

    try:
        number_bad_files = 0
        file_count = 0

        # Get the list of participants with open files to process
        participants = Participant.objects.filter(files_to_process__isnull=False).distinct()
        print("processing files for the following users: %s" % ",".join(participants.values_list('patient_id', flat=True)))

        for participant in participants:

            print(f'{datetime.now()} processing {participant.patient_id},',
                  f'{participant.files_to_process.exclude(deleted=True).count()} files remaining')

            for fp in participant.files_to_process.exclude(deleted=True).all():
                print(fp.s3_file_path)
                event={'Records': [{
                    's3':{
                        'object':{
                            'key': fp.s3_file_path
                        }
                    }
                }]}


                # Process the desired number of files and calculate the number of unprocessed files
                retval = do_process_user_file_chunks_lambda_handler(event, [])

                print(retval)

                file_count += 1

                if count > 0 and file_count > count:
                    break

    finally:
        FileProcessLock.unlock()

    error_handler.raise_errors()
    raise EverythingWentFine(DATA_PROCESSING_NO_ERROR_STRING)


def do_process_user_file_chunks_lambda_handler(event, context):
    """
    Chunker designed to be called by a lambda that is triggered by a new file being written to
    the 'RAW_DATA' folder of a S3 bucket. Receives a data structure that contains the path of
    the file to process, pull the data, put it into s3 bins. Run the file through
    the appropriate logic path based on file type.

    If a file is empty put its ftp object to the empty_files_list, we can't delete objects
    in-place while iterating over the db.

    All files except for the audio recording files are in the form of CSVs, most of those files
    can be separated by "time bin" (separated into one-hour chunks) and concatenated and sorted
    trivially. A few files, call log, identifier file, and wifi log, require some triage
    beforehand.  The debug log cannot be correctly sorted by time for all elements, because it
    was not actually expected to be used by researchers, but is apparently quite useful.

    Any errors are themselves concatenated using the passed in error handler.
    """

    error_handler = ErrorHandler()

    # Declare a defaultdict containing a tuple of two double ended queues (deque, pronounced "deck")
    all_binified_data = defaultdict(lambda: (deque(), deque()))
    ftps_to_remove = set()
    survey_id_dict = {}

    for record in event['Records']:
        full_s3_path = record['s3']['object']['key']
        key_values = full_s3_path.split('/')

        # out of paranoia, verify once again that the file is in the RAW_DATA directory
        if 'RAW_DATA' not in key_values[0]:

            logger.error('S3 path {0} does not appear to be in RAW_DATA'.format(full_s3_path))
            return {
                'statusCode': 200,
                'body': json.dumps('False positive!')
            }

        study_object_id = key_values[1]
        participant_id = key_values[2]

        try:
            participant = Participant.objects.get(patient_id = participant_id)
        except Participant.DoesNotExist as e:
            logger.error('Could not find participant {0} for file to process {1}'.format(participant_id, full_s3_path))
            return {
                'statusCode': 200,
                'body': json.dumps('Lambda failed!')
            }

        # another paranoia check, but lets make sure that the study_object_id is correct for this participant
        if participant.study.object_id != study_object_id:
            logger.error('Could not find participant {0} for file to process {1}'.format(participant_id, full_s3_path))
            return {
                'statusCode': 200,
                'body': json.dumps('Lambda failed!')
            }

        # an file with no extension means we may need to create RSA keys for this participant
        # lets investigate!
        _, file_extension = os.path.splitext(full_s3_path)
        if not file_extension:

            # first check to see if a key pair already exists
            if check_for_client_key_pair(participant_id, study_object_id) is True:

                logger.error('Key pair already exists for {0}: {1}'.format(study_object_id, participant_id))

                return {
                    'statusCode': 200,
                    'body': json.dumps('Key pair already exists for {0}: {1}'.format(study_object_id, participant_id))
                }

            else:
                logger.info('Generating key pair for {0}: {1}'.format(study_object_id, participant_id))
                create_client_key_pair(participant_id, study_object_id)

                return {
                    'statusCode': 200,
                    'body': json.dumps('Created key pair for {0}: {1}'.format(study_object_id, participant_id))
                }

        else:

            try:
                file_to_process = participant.files_to_process.exclude(deleted=True).get(s3_file_path=full_s3_path)
            except FileToProcess.MultipleObjectsReturned as e:
                # sometimes there are multiple entries on files_to_process with the same s3 path,
                # i am not sure why this happens, but i think that it could be OK just to
                # take the first and delete the others
                the_first_file = True
                for fp in participant.files_to_process.exclude(deleted=True).filter(s3_file_path=full_s3_path):
                    if the_first_file == True:
                        file_to_process = fp
                        the_first_file = False
                    else:
                        ftps_to_remove.add(fp.id)
            except FileToProcess.DoesNotExist as e:
                logger.error('Could not find file to process {0} for participant {1}'.format(full_s3_path, participant_id))
                return {
                    'statusCode': 200,
                    'body': json.dumps('Lambda failed!')
                }

            print('found file_to_process: ' + str(file_to_process.as_dict()))

            data = batch_retrieve_for_processing(file_to_process)

            # If we encountered any errors in retrieving the files for processing, they have been
            # lumped together into data['exception']. Raise them here to the error handler and
            # move to the next file.
            if data['exception']:
                logger.error("\n" + data['ftp']['s3_file_path'])
                logger.error(data['traceback'])
                ################################################################
                # YOU ARE SEEING THIS EXCEPTION WITHOUT A STACK TRACE
                # BECAUSE IT OCCURRED INSIDE POOL.MAP, ON ANOTHER THREAD
                ################################################################
                raise data['exception']

            # call function to further process the data
            if data['data_type'] in file_processing_func:
                print(f'calling file processing func on {data["data_type"]}')
                file_processing_func[data['data_type']](data)
                # call API to send calculated measures to data aggregator

            if data['chunkable']:
                newly_binified_data, survey_id_hash = process_csv_data(data)
                if data['data_type'] in SURVEY_DATA_FILES:
                    survey_id_dict[survey_id_hash] = resolve_survey_id_from_file_name(data['ftp']["s3_file_path"])

                if newly_binified_data:
                    append_binified_csvs(all_binified_data, newly_binified_data, data['ftp'])
                else:  # delete empty files from FilesToProcess
                    ftps_to_remove.add(data['ftp']['id'])

            # if not data['chunkable']
            else:
                timestamp = clean_java_timecode(data['ftp']["s3_file_path"].rsplit("/", 1)[-1][:-4])
                # Since we aren't binning the data by hour, just create a ChunkRegistry that
                # points to the already existing S3 file.
                ChunkRegistry.register_unchunked_data(
                    data['data_type'],
                    timestamp,
                    data['ftp']['s3_file_path'],
                    data['ftp']['study'].pk,
                    data['ftp']['participant'].pk,
                    data['file_contents'],
                )
                ftps_to_remove.add(data['ftp']['id'])

    more_ftps_to_remove, number_bad_files = upload_binified_data(all_binified_data, error_handler, survey_id_dict)
    ftps_to_remove.update(more_ftps_to_remove)
    # Actually delete the processed FTPs from the database
    FileToProcess.objects.filter(pk__in=ftps_to_remove).delete()
    # Garbage collect to free up memory
    gc.collect()

    return {
        'statusCode': 200,
        'body': json.dumps('Lambda finished!')
    }


def process_file_chunks():
    """
    This is the function that is called from the command line.  It runs through all new files
    that have been uploaded and 'chunks' them. Handles logic for skipping bad files, raising
    errors appropriately.
    This is primarily called manually during testing and debugging.
    """
    # Initialize the process and ensure there is no other process running at the same time
    error_handler = ErrorHandler()
    if FileProcessLock.islocked():
        raise ProcessingOverlapError("Data processing overlapped with a previous data indexing run.")
    FileProcessLock.lock()

    try:
        number_bad_files = 0

        # Get the list of participants with open files to process
        participants = Participant.objects.filter(files_to_process__isnull=False).distinct()
        print("processing files for the following users: %s" % ",".join(participants.values_list('patient_id', flat=True)))

        for participant in participants:
            while True:
                previous_number_bad_files = number_bad_files
                starting_length = participant.files_to_process.exclude(deleted=True).count()

                print("%s processing %s, %s files remaining" % (datetime.now(), participant.patient_id, starting_length))

                # Process the desired number of files and calculate the number of unprocessed files
                number_bad_files += do_process_user_file_chunks(
                        count=FILE_PROCESS_PAGE_SIZE,
                        error_handler=error_handler,
                        skip_count=number_bad_files,
                        participant=participant,
                )

                # If no files were processed, quit processing
                if (participant.files_to_process.exclude(deleted=True).count() == starting_length
                        and previous_number_bad_files == number_bad_files):
                    # Cases:
                    #   every file broke, might as well fail here, and would cause infinite loop otherwise.
                    #   no new files.
                    break
    finally:
        FileProcessLock.unlock()

    error_handler.raise_errors()
    raise EverythingWentFine(DATA_PROCESSING_NO_ERROR_STRING)


def do_process_user_file_chunks(count: int, error_handler: ErrorHandler, skip_count: int,
                                participant: Participant):
    """
    Run through the files to process, pull their data, put it into s3 bins. Run the file through
    the appropriate logic path based on file type.

    If a file is empty put its ftp object to the empty_files_list, we can't delete objects
    in-place while iterating over the db.

    All files except for the audio recording files are in the form of CSVs, most of those files
    can be separated by "time bin" (separated into one-hour chunks) and concatenated and sorted
    trivially. A few files, call log, identifier file, and wifi log, require some triage
    beforehand.  The debug log cannot be correctly sorted by time for all elements, because it
    was not actually expected to be used by researchers, but is apparently quite useful.

    Any errors are themselves concatenated using the passed in error handler.

    In a single call to this function, count files will be processed, starting from file number
    skip_count. The first skip_count files are expected to be files that have previously errored
    in file processing.
    """
    # Declare a defaultdict containing a tuple of two double ended queues (deque, pronounced "deck")
    all_binified_data = defaultdict(lambda: (deque(), deque()))
    ftps_to_remove = set()
    # The ThreadPool enables downloading multiple files simultaneously from the network, and continuing
    # to download files as other files are being processed, making the code as a whole run faster.
    pool = ThreadPool(CONCURRENT_NETWORK_OPS)
    survey_id_dict = {}

    # A Django query with a slice (e.g. .all()[x:y]) makes a LIMIT query, so it
    # only gets from the database those FTPs that are in the slice.
    print(participant.as_native_python())
    print(len(participant.files_to_process.exclude(deleted=True).all()))
    print(count)
    print(skip_count)

    files_to_process = participant.files_to_process.exclude(deleted=True).all()

    for data in pool.map(batch_retrieve_for_processing,
                         files_to_process[skip_count:count+skip_count],
                         chunksize=1):
        with error_handler:
            # If we encountered any errors in retrieving the files for processing, they have been
            # lumped together into data['exception']. Raise them here to the error handler and
            # move to the next file.
            if data['exception']:
                print("\n" + data['ftp']['s3_file_path'])
                print(data['traceback'])
                ################################################################
                # YOU ARE SEEING THIS EXCEPTION WITHOUT A STACK TRACE
                # BECAUSE IT OCCURRED INSIDE POOL.MAP ON ANOTHER THREAD
                ################################################################
                raise data['exception']

            if data['chunkable']:
                newly_binified_data, survey_id_hash = process_csv_data(data)
                if data['data_type'] in SURVEY_DATA_FILES:
                    survey_id_dict[survey_id_hash] = resolve_survey_id_from_file_name(data['ftp']["s3_file_path"])

                if newly_binified_data:
                    append_binified_csvs(all_binified_data, newly_binified_data, data['ftp'])
                else:  # delete empty files from FilesToProcess
                    ftps_to_remove.add(data['ftp']['id'])
                continue

            # if not data['chunkable']
            else:
                timestamp = clean_java_timecode(data['ftp']["s3_file_path"].rsplit("/", 1)[-1][:-4])
                # Since we aren't binning the data by hour, just create a ChunkRegistry that
                # points to the already existing S3 file.
                ChunkRegistry.register_unchunked_data(
                    data['data_type'],
                    timestamp,
                    data['ftp']['s3_file_path'],
                    data['ftp']['study'].pk,
                    data['ftp']['participant'].pk,
                    data['file_contents'],
                )
                ftps_to_remove.add(data['ftp']['id'])

    pool.close()
    pool.terminate()
    more_ftps_to_remove, number_bad_files = upload_binified_data(all_binified_data, error_handler, survey_id_dict)
    ftps_to_remove.update(more_ftps_to_remove)
    # Actually delete the processed FTPs from the database
    FileToProcess.objects.filter(pk__in=ftps_to_remove).delete()
    # Garbage collect to free up memory
    gc.collect()
    return number_bad_files


def upload_binified_data(binified_data, error_handler, survey_id_dict):
    """ Takes in binified csv data and handles uploading/downloading+updating
        older data to/from S3 for each chunk.
        Returns a set of concatenations that have succeeded and can be removed.
        Returns the number of failed FTPS so that we don't retry them.
        Raises any errors on the passed in ErrorHandler."""
    failed_ftps = set([])
    ftps_to_retire = set([])
    upload_these = []
    for data_bin, (data_rows_deque, ftp_deque) in binified_data.items():
        with error_handler:
            try:
                study_id, user_id, data_type, time_bin, original_header = data_bin
                # data_rows_deque may be a generator; here it is evaluated
                rows = list(data_rows_deque)
                ensure_sorted_by_timestamp(rows)

                # changed file name to be datetime string corresponding to the first row in the file, to hopefully
                # avoid any collisions resulting from interleaved writes (i.e. two different raw files that both
                # contain date for the same time bin)
                updated_header, first_date_string = convert_unix_to_human_readable_timestamps(original_header, rows)
                chunk_path = construct_s3_chunk_path(study_id, user_id, data_type, first_date_string)

                new_contents = construct_csv_string(updated_header, rows)

                if data_type in SURVEY_DATA_FILES:
                    # We need to keep a mapping of files to survey ids, that is handled here.
                    survey_id_hash = study_id, user_id, data_type, original_header
                    survey_id = survey_id_dict[survey_id_hash]
                else:
                    survey_id = None
                    
                chunk_params = {
                    "study_id": study_id,
                    "user_id": user_id,
                    "data_type": data_type,
                    "chunk_path": chunk_path,
                    "time_bin": time_bin,
                    "survey_id": survey_id
                }

                upload_these.append((chunk_params, chunk_path, codecs.encode(new_contents, "zip"), study_id))
            except Exception as e:
                # Here we catch any exceptions that may have arisen, as well as the ones that we raised
                # ourselves (e.g. HeaderMismatchException). Whichever FTP we were processing when the
                # exception was raised gets added to the set of failed FTPs.
                failed_ftps.update(ftp_deque)
                print(e)
                print("FAILED TO UPDATE: study_id:%s, user_id:%s, data_type:%s, time_bin:%s, header:%s "
                      % (study_id, user_id, data_type, time_bin, updated_header))
                raise
            else:
                # If no exception was raised, the FTP has completed processing. Add it to the set of
                # retireable (i.e. completed) FTPs.
                ftps_to_retire.update(ftp_deque)

    # only use thread pool if we are running in celery, not if running serverless
    if IS_SERVERLESS is False:
        pool = ThreadPool(CONCURRENT_NETWORK_OPS)
        errors = pool.map(batch_upload, upload_these, chunksize=1)
        for err_ret in errors:
            if err_ret['exception']:
                print(err_ret['traceback'])
                raise err_ret['exception']

        pool.close()
        pool.terminate()

    else:
        for upload_tuple in upload_these:
            batch_upload(upload_tuple)

    # The things in ftps to retire that are not in failed ftps.
    # len(failed_ftps) will become the number of files to skip in the next iteration.
    return ftps_to_retire.difference(failed_ftps), len(failed_ftps)


"""################################ S3 Stuff ################################"""


def construct_s3_chunk_path(study_id, user_id, data_type, datetime_string: str) -> str:
    """ S3 file paths for chunks are of this form:
        CHUNKED_DATA/study_id/user_id/data_type/datetime_string.csv 
        assumes that datetime_string has been formatted prior to being used here """

    study_id = study_id.decode() if isinstance(study_id, bytes) else study_id
    user_id = user_id.decode() if isinstance(user_id, bytes) else user_id
    data_type = data_type.decode() if isinstance(data_type, bytes) else data_type

    return "%s/%s/%s/%s/%s.csv" % (
        CHUNKS_FOLDER,
        study_id,
        user_id,
        data_type,
        datetime_string
    )


"""################################# Key ####################################"""


def file_path_to_data_type(file_path: str):
    # Look through each folder name in file_path to see if it corresponds to a data type. Due to
    # a dumb mistake ages ago the identifiers file has an underscore where it should have a
    # slash, and we have to handle that case.  Also, it looks like we are hitting that case with
    # the identifiers file separately but without any slashes in it, sooooo we need to for-else.
    for file_piece in file_path.split('/'):
        data_type = UPLOAD_FILE_TYPE_MAPPING.get(file_piece, None)
        if data_type and "identifiers" in data_type:
            return IDENTIFIERS
        if data_type:
            return data_type
    else:
        if "identifiers" in file_path:
            return IDENTIFIERS
        if "ios/log" in file_path:
            return IOS_LOG_FILE
    # If no data type has been selected; i.e. if none of the data types are present in file_path,
    # raise an error
    raise Exception("data type unknown: %s" % file_path)


def ensure_sorted_by_timestamp(l: list):
    """ According to the docs the sort method on a list is in place and should
        faster, this is how to declare a sort by the first column (timestamp). """
    l.sort(key=lambda x: int(x[0]))


def convert_unix_to_human_readable_timestamps(header: bytes, rows: list) -> List[bytes]:
    """ Adds a new column to the end which is the unix time represented in
    a human readable time format.  Returns an appropriately modified header and
    the datetime string corresponding to the first row """
    for row in rows:
        unix_millisecond = int(row[0])
        time_string = unix_time_to_string(unix_millisecond // 1000)
        # this line 0-pads millisecond values that have leading 0s.
        time_string += b".%03d" % (unix_millisecond % 1000)
        row.insert(1, time_string)
    header = header.split(b",")
    header.insert(1, b"UTC time")
    return b",".join(header), rows[0][1].decode()


def binify_from_timecode(unix_ish_time_code_string: bytes) -> int:
    """ Takes a unix-ish time code (accepts unix millisecond), and returns an
        integer value of the bin it should go in. """
    actually_a_timecode = clean_java_timecode(unix_ish_time_code_string)  # clean java time codes...
    return actually_a_timecode // CHUNK_TIMESLICE_QUANTUM #separate into nice, clean hourly chunks!


"""############################## Standard CSVs #############################"""


def binify_csv_rows(rows_list: list, study_id: str, user_id: str, data_type: str, header: bytes) -> DefaultDict[tuple, deque]:
    """ Assumes a clean csv with element 0 in the rows column as a unix(ish) timestamp.
        Sorts data points into the appropriate bin based on the rounded down hour
        value of the entry's unix(ish) timestamp. (based CHUNK_TIMESLICE_QUANTUM)
        Returns a dict of form {(study_id, user_id, data_type, time_bin, header):rows_lists}. """
    ret = defaultdict(deque)
    for row in rows_list:
        # discovered August 7 2017, looks like there was an empty line at the end
        # of a file? row was a [''].
        if row and row[0]:
            ret[(study_id, user_id, data_type, binify_from_timecode(row[0]), header)].append(row)
    return ret


def append_binified_csvs(old_binified_rows: DefaultDict[tuple, deque],
                         new_binified_rows: DefaultDict[tuple, deque],
                         file_to_process: dict):
    """ Appends binified rows to an existing binified row data structure.
        Should be in-place. """
    for data_bin, rows in new_binified_rows.items():
        old_binified_rows[data_bin][0].extend(rows)  # Add data rows
        old_binified_rows[data_bin][1].append(file_to_process['id'])  # Add ftp


def process_csv_data(data: dict):
    # In order to reduce memory overhead this function takes a dictionary instead of args
    """ Constructs a binified dict of a given list of a csv rows,
        catches csv files with known problems and runs the correct logic.
        Returns None If the csv has no data in it. """
    participant = data['ftp']['participant']

    if participant.os_type == Participant.ANDROID_API:
        # Do fixes for Android
        if data["data_type"] == ANDROID_LOG_FILE:
            data['file_contents'] = fix_app_log_file(data['file_contents'], data['ftp']['s3_file_path'])

        header, csv_rows_list = csv_to_list(data['file_contents'])
        if data["data_type"] != ACCELEROMETER:
            # If the data is not accelerometer data, convert the generator to a list.
            # For accelerometer data, the data is massive and so we don't want it all
            # in memory at once.
            csv_rows_list = [r for r in csv_rows_list]

        if data["data_type"] == CALL_LOG:
            header = fix_call_log_csv(header, csv_rows_list)
        if data["data_type"] == WIFI:
            header = fix_wifi_csv(header, csv_rows_list, data['ftp']['s3_file_path'])
    else:
        # Do fixes for iOS
        header, csv_rows_list = csv_to_list(data['file_contents'])
        if data["data_type"] != ACCELEROMETER:
            csv_rows_list = [r for r in csv_rows_list]

    # Memory saving measure: this data is now stored in its entirety in csv_rows_list
    del data['file_contents']

    # Do these fixes for data whether from Android or iOS
    if data["data_type"] == IDENTIFIERS:
        header = fix_identifier_csv(header, csv_rows_list, data['ftp']['s3_file_path'])
    if data["data_type"] == SURVEY_TIMINGS:
        header = fix_survey_timings(header, csv_rows_list, data['ftp']['s3_file_path'])

    header = b",".join([column_name.strip() for column_name in header.split(b",")])
    if csv_rows_list:
        return (
            # return item 1: the data as a defaultdict
            binify_csv_rows(
                csv_rows_list,
                data['ftp']['study'].object_id.encode(),
                data['ftp']['participant'].patient_id,
                data["data_type"],
                header
            ),
            # return item 2: the tuple that we use as a key for the defaultdict
            (data['ftp']['study'].object_id.encode(), data['ftp']['participant'].patient_id, data["data_type"], header)
        )
    else:
        return None, None


"""############################ CSV Fixes #####################################"""


def fix_survey_timings(header: bytes, rows_list: List[bytes], file_path: str) -> bytes:
    """ Survey timings need to have a column inserted stating the survey id they come from."""
    survey_id = file_path.rsplit("/", 2)[1].encode()
    for row in rows_list:
        row.insert(2, survey_id)
    header_list = header.split(b",")
    header_list.insert(2, b"survey id")
    return b",".join(header_list)


def fix_call_log_csv(header: bytes, rows_list: list) -> bytes:
    """ The call log has poorly ordered columns, the first column should always be
        the timestamp, it has it in column 3.
        Note: older versions of the app name the timestamp column "date". """
    for row in rows_list:
        row.insert(0, row.pop(2))
    header_list = header.split(b",")
    header_list.insert(0, header_list.pop(2))
    return b",".join(header_list)


def fix_identifier_csv(header: bytes, rows_list: list, file_name: str) -> bytes:
    """ The identifiers file has its timestamp in the file name. """
    time_stamp = file_name.rsplit("_", 1)[-1][:-4].encode() + b"000"
    return insert_timestamp_single_row_csv(header, rows_list, time_stamp)


def fix_wifi_csv(header: bytes, rows_list: list, file_name: str):
    """ Fixing wifi requires inserting the same timestamp on EVERY ROW.
    The wifi file has its timestamp in the filename. """
    time_stamp = file_name.rsplit("/", 1)[-1][:-4].encode()

    # the last row is a new line, have to slice.
    for row in rows_list[:-1]:
        row = row.insert(0, time_stamp)

    if rows_list:
        # remove last row (encountered an empty wifi log on sunday may 8 2016)
        rows_list.pop(-1)

    return b"timestamp," + header


def fix_app_log_file(file_contents, file_path):
    """ The log file is less of a csv than it is a time enumerated list of
        events, with the time code preceding each row.
        We insert a base value, a new row stating that a new log file was created,
        which allows us to guarantee at least one timestamp in the file."""
    time_stamp = file_path.rsplit("/", 1)[-1][:-4].encode()
    rows_list = file_contents.splitlines()
    rows_list[0] = time_stamp + b" New app log file created"
    new_rows = []
    for row in rows_list:
        row_elements = row.split(b" ", 1)  # split first whitespace, element 0 is a java timecode
        try:
            int(row_elements[0])  # grab first element, check if it is a valid int
            new_rows.append(row_elements)
        except ValueError as e:
            if (b"bluetooth Failure" == row[:17] or
                b"our not-quite-race-condition" == row[:28] or
                b"accelSensorManager" in row[:18] or  # this actually covers 2 cases
                b"a sessionactivity tried to clear the" == row[:36]
            ):
                # Just drop matches to the above lines
                continue
            else:
                # Previously this was a whitelist of broken lines to explicitly insert a timecode
                # on, but now it is generalized:
                # 'new_rows[-1][0]' is the timecode of the previous line in the log.
                new_rows.append((new_rows[-1][0], row))
                continue

    return b"timestamp, event\n" + b"\n".join(b",".join(row) for row in new_rows)


"""###################################### CSV Utils ##################################"""


def insert_timestamp_single_row_csv(header: bytes, rows_list: list, time_stamp: bytes) -> bytes:
    """ Inserts the timestamp field into the header of a csv, inserts the timestamp
        value provided into the first column.  Returns the new header string."""
    header_list = header.split(b",")
    header_list.insert(0, b"timestamp")
    rows_list[0].insert(0, time_stamp)
    return b",".join(header_list)


def csv_to_list(csv_string: bytes) -> (bytes, Generator):
    """ Grab a list elements from of every line in the csv, strips off trailing whitespace. dumps
    them into a new list (of lists), and returns the header line along with the list of rows. """
    # This code is more memory efficient than fast by using a generator
    # Note that almost all of the time is spent in the per-row for-loop
    def split_yielder(l):
        for row in l:
            yield row.split(b",")
    header = csv_string[:csv_string.find(b"\n")]
    lines = csv_string.splitlines()
    # Remove the header
    lines.pop(0)  # This line is annoyingly slow, but its fine...
    del csv_string  # To clear up memory
    return header, split_yielder(lines)


def construct_csv_string(header: bytes, rows_list: List[bytes]) -> bytes:
    """ Takes a header list and a csv and returns a single string of a csv.
        Now handles unicode errors.  :D :D :D """
    # The old, compact list comprehension was, it turned out, both nonperformant and of an
    # incomprehensible memory order. This is ~1.5x faster, and has a much clearer memory order.

    def deduplicate(seq):
        # highly optimized order preserving deduplication function.
        seen = set()
        seen_add = seen.add
        return [x for x in seq if not (x in seen or seen_add(x))]

    rows = []
    for row_items in rows_list:

        try:
            rows.append(b",".join(row_items))
        except TypeError:
            print("######################################################################3")
            pprint(row_items)
            print("######################################################################3")
            raise

    del rows_list, row_items

    # we need to ensure no duplicates
    rows = deduplicate(rows)
    ret = header
    for row in rows:
        ret += b"\n" + row
    return ret


def clean_java_timecode(java_time_code_string: bytes) -> int:
    """ converts millisecond time (string) to an integer normal unix time. """
    return int(java_time_code_string[:10])


def unix_time_to_string(unix_time: int) -> bytes:
    return datetime.utcfromtimestamp(unix_time).strftime(API_TIME_FORMAT).encode()


""" Batch Operations """


def batch_retrieve_for_processing(ftp_as_object: FileToProcess) -> dict:
    """ Used for mapping an s3_retrieve function. """
    # Convert the ftp object to a dict so we can use __getattr__
    ftp = ftp_as_object.as_dict()

    data_type = file_path_to_data_type(ftp['s3_file_path'])

    # Create a dictionary to populate and return
    ret = {
        'ftp': ftp,
        "data_type": data_type,
        'exception': None,
        "file_contents": "",
        "traceback": None,
        'chunkable': data_type in CHUNKABLE_FILES,
    }

    # Try to retrieve the file contents. If any errors are raised, store them to be raised by the
    # parent function
    try:
        print(ftp['s3_file_path'] + ", getting data...")
        ret['file_contents'] = s3_retrieve(ftp['s3_file_path'], ftp["study"].object_id.encode(), raw_path=True)
    except Exception as e:
        traceback.print_exc()
        ret['traceback'] = sys.exc_info()
        ret['exception'] = e
    return ret


def batch_upload(upload: Tuple[dict, str, bytes, str]):
    """ Used for mapping an s3_upload function.  the tuple is unpacked, can only have one parameter. """
    ret = {'exception': None, 'traceback': None}
    try:
        if len(upload) != 4:
            # upload should have length 4; this is for debugging if it doesn't
            print(upload)
        chunk, chunk_path, new_contents, study_object_id = upload
        del upload

        if "b'" in chunk_path:
            raise Exception(chunk_path)

        s3_upload(chunk_path, codecs.decode(new_contents, "zip"), study_object_id, raw_path=True)
        print("data uploaded!", chunk_path)

        if isinstance(chunk, ChunkRegistry):
            # If the contents are being appended to an existing ChunkRegistry object
            chunk.file_size = len(new_contents)
            chunk.update_chunk_hash(new_contents)

        else:
            # If a new ChunkRegistry object is being created
            # Convert the ID's used in the S3 file names into primary keys for making ChunkRegistry FKs
            participant_pk, study_pk = Participant.objects.filter(patient_id=chunk['user_id']).values_list('pk', 'study_id').get()
            if chunk['survey_id']:
                survey_pk = Survey.objects.filter(object_id=chunk['survey_id']).values_list('pk', flat=True).get()
            else:
                survey_pk = None

            ChunkRegistry.register_chunked_data(
                chunk['data_type'],
                chunk['time_bin'],
                chunk['chunk_path'],
                new_contents,  # unlikely to be huge
                study_pk,
                participant_pk,
                survey_pk,
            )

    # it broke. print stacktrace for debugging
    except Exception as e:
        traceback.print_exc()
        ret['traceback'] = sys.exc_info()
        ret['exception'] = e

    return ret


""" Exceptions """
class HeaderMismatchException(Exception): pass
class ChunkFailedToExist(Exception): pass


# This is useful for performance testing, replace the real threadpool with this one and everything
# will suddenly be single-threaded, making it much easier to profile.
# class ThreadPool():
#     def map(self, *args, **kwargs): #the existance of that self variable is key
#         # we actually want to cut off any threadpool args, which is conveniently easy because map does not use kwargs!
#         return map(*args)
#     def terminate(self): pass
#     def close(self): pass
#     def __init__(self, *args,**kwargs):
#         pass
