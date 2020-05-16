from libs.data_download_helper import copy_data_to_box
from os import getenv, environ
import datetime
from config.constants import API_TIME_FORMAT
from libs.ses import ses_send_email
from database.pipeline_models import PipelineExecutionTracking
import json


def run():

    ret_val = None

    pipeline_function = getenv('pipeline_function')
    pipeline_id = int(getenv('pipeline_id'))

    if not pipeline_id:
        raise ValueError("pipeline_id either wasn't found in the environment, or it was set to empty.")

    PipelineExecutionTracking.pipeline_started(pipeline_id, datetime.datetime.now())

    if pipeline_function == 'copy_to_box':

        participants = None
        if getenv('participants'):
            participants = json.loads(getenv('participants'))

        datastreams = None
        if getenv('datastreams'):
            datastreams = json.loads(getenv('datastreams'))

        download_request = {
            'username': getenv('owner_id'),
            'datetime': getenv('request_datetime'),
            'study_object_id': getenv('study_object_id'),
            'datastreams': datastreams,
            'patient_ids': participants,
            'box_directory': getenv('box_directory'),
        }

        ret_val = copy_data_to_box(download_request)

    if ret_val['status'] == 200:
        email_message = f'{pipeline_function} request {pipeline_id} submitted ' \
                        f'{getenv("request_datetime")} by {getenv("owner_id")} completed successfully at ' \
                        f'{datetime.datetime.now().strftime(API_TIME_FORMAT)}'

        email_subject = f'{pipeline_function} completed successfully'
        PipelineExecutionTracking.pipeline_completed(pipeline_id, datetime.datetime.now())

    else:
        email_message = f'{pipeline_function} request {pipeline_id} submitted ' \
                        f'{getenv("request_datetime")} by {getenv("owner_id")} failed at ' \
                        f'{datetime.datetime.now().strftime(API_TIME_FORMAT)} with message: {ret_val["body"]}'
        email_subject = f'{pipeline_function} completed successfully'
        PipelineExecutionTracking.pipeline_crashed(pipeline_id, datetime.datetime.now(), ret_val["body"])

    ses_send_email(email_message, email_subject, getenv('destination_email_address'))

    print(ret_val)


if __name__ == '__main__':
    for i,v in environ.items():
        print(f'{i}={v}')
    run()
