import os
import datetime
from config.constants import API_TIME_FORMAT, ALL_DATA_STREAMS
from pipeline.run import run
import subprocess
import json


if __name__ == "__main__":

    download_request = {
        'username': 'cameron',
        'datetime': datetime.datetime.now().strftime(API_TIME_FORMAT),

    }

    owner_id = 'cameron'
    request_datetime = datetime.datetime.now()
    pipeline_id = 1
    object_id = 'cOr8H1pwhgK61yjEhbs8wWlv'
    freq = 'manual'
    pipeline_function = 'copy_to_box'
    destination_email_addresses = ['cameron.craddock@gmail.com']
    datastreams = ALL_DATA_STREAMS
    participants = ['1adkek2h', '37sb8wql', '48hekr1g', '51opds1x', '63zkl16v', 'bayw6h9b', 'ctyscd4b', 'derjasj9', 'drs2jy5f', 'fi577z38', 'gqpcflwk', 'kyys2qo6', 'naucsx6v', 'rjcs3hyw', 'rkem5aou', 'synympvt', 'xw31f35c']
    box_directory = 'beiwe_export'
    data_start_datetime = None
    data_end_datetime = None


    environment = [
        {
            'name': 'owner_id',
            'value': str(owner_id),
        },
        {
            'name': 'request_datetime',
            'value': request_datetime.strftime(API_TIME_FORMAT),
        },
        {
            'name': 'pipeline_function',
            'value': pipeline_function,
        },
        {
            'name': 'pipeline_id',
            'value': str(pipeline_id),
        },
        {
            'name': 'study_object_id',
            'value': str(object_id),
        },
        {
            'name': 'FREQ',
            'value': freq,
        },
        {
            'name': 'destination_email_address',
            'value': ','.join(destination_email_addresses),
        },
        {
            'name': 'data_start_datetime',
            'value': data_start_datetime.strftime(API_TIME_FORMAT) if data_start_datetime else '',
        },
        {
            'name': 'data_end_datetime',
            'value': data_end_datetime.strftime(API_TIME_FORMAT) if data_end_datetime else '',
        },
        {
            'name': 'participants',
            'value': json.dumps(participants),
        },
        {
            'name': 'datastreams',
            'value': json.dumps(datastreams),
        },
        {
            'name': 'box_directory',
            'value': box_directory,
        }
    ]

    new_environment=[]
    for env in environment:
        new_environment+=["-e",f"{env['name']}={env['value']}"]

    print(f'running with {new_environment}')
    #run()
    docker_command=['docker', 'run', '-v', '/home/ubuntu/beiwe-backend:/home/beiwe-backend'] + new_environment + \
            ['beiwe-analysis:latest', '/bin/bash', '/home/beiwe-backend/pipeline/runner.sh']
    #print(docker_command)
    subprocess.check_call(docker_command)
