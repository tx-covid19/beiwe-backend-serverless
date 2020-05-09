from os.path import abspath as _abspath
from sys import path as _path
_one_folder_up = _abspath(__file__).rsplit('/',2)[0]
_path.insert(1, _one_folder_up)

from config import load_django
from config.constants import RAW_DATA_FOLDER, KEYS_FOLDER
from datetime import datetime

from database.data_access_models import FileToProcess
from libs.s3 import conn, S3_BUCKET, s3_list_files, s3_move
from pprint import pprint

print("start:", datetime.now())

s3_file_paths = s3_list_files(RAW_DATA_FOLDER)

for s3_file_path in s3_file_paths:
    if 'keys' in s3_file_path:
        new_path = s3_file_path.replace(RAW_DATA_FOLDER, KEYS_FOLDER).replace('keys/','')
        print(f'moving {s3_file_path} to {new_path}')
        s3_move(s3_file_path, new_path)
