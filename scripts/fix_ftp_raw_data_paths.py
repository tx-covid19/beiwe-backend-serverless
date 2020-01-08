from os.path import abspath as _abspath
from sys import path as _path
_one_folder_up = _abspath(__file__).rsplit('/',2)[0]
_path.insert(1, _one_folder_up)

from config import load_django
from config.constants import RAW_DATA_FOLDER
from datetime import datetime

from database.data_access_models import FileToProcess
from libs.s3 import conn, S3_BUCKET
from pprint import pprint

print("start:", datetime.now())

for ftp in FileToProcess.objects.all():

    #study_pk = Study.objects.filter(object_id=study_object_id).values_list('pk', flat=True).get()
    study_object_id = ftp.study.object_id
    print(f'{study_object_id}: {ftp.s3_file_path}')

    if ftp.s3_file_path[:len(RAW_DATA_FOLDER)] != RAW_DATA_FOLDER:
        if ftp.s3_file_path[:len(study_object_id)] == study_object_id:
            ftp.s3_file_path = '/'.join([RAW_DATA_FOLDER, ftp.s3_file_path])
        else:
            ftp.s3_file_path = '/'.join([RAW_DATA_FOLDER, study_object_id, ftp.s3_file_path])
        ftp.save()

    print(f'{study_object_id}: {ftp.s3_file_path}')

    #raw_data_study_dir = '/'.join([RAW_DATA_DIR, study_object_id])
    #if file_path[:len(raw_data_study_dir)] == raw_data_study_dir:
        #cls.objects.create(s3_file_path=file_path, study_id=study_pk, **kwargs)
    #else:
        #cls.objects.create(s3_file_path=raw_data_study_dir + '/' + file_path, study_id=study_pk, **kwargs)
