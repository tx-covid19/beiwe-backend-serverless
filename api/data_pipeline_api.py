import os
import re
import json
from flask import Blueprint, flash, redirect, abort, request, session
import datetime
from database.study_models import Study
from database.user_models import Participant
from libs.admin_authentication import authenticate_researcher_study_access, get_session_researcher
from libs.sentry import make_error_sentry
import libs.dateutils as dateutils
from pipeline.boto_helpers import get_boto_client
from pipeline.index import create_one_job, refresh_data_access_credentials, terminate_job
from validate_email import validate_email
from pipeline.configuration_getters import get_current_region

data_pipeline_api = Blueprint('data_pipeline_api', __name__)
pipeline_region = os.getenv("pipeline_region", None)

@data_pipeline_api.route('/run-manual-code/<string:study_id>', methods=['POST'])
@authenticate_researcher_study_access
def run_manual_code(study_id):
    """
    Create an AWS Batch job for the Study specified
    :param study_id: Primary key of a Study
    """

    session_researcher = get_session_researcher()

    destination_email_addresses_string = ''
    if 'destination_email_addresses' in request.values:
        destination_email_addresses_string = request.values['destination_email_addresses']
        destination_email_addresses = [d.strip() for d in filter(None, re.split("[, \?:;]+", destination_email_addresses_string))]
        for email_address in destination_email_addresses:
            if not validate_email(email_address):
                flash('Email address {0} in ({1}) does not appear to be a valid email address.'.format(email_address, destination_email_addresses_string), category='danger')
                return redirect('/data-pipeline/{:s}'.format(study_id))
        destination_email_addresses_string = ','.join(destination_email_addresses)

    job_type = ''
    if 'job_type' in request.values:
        job_type = request.values['job_type']

    participants = []
    if 'participants' in request.values:
        participants = request.form.getlist('participants')

    data_start_time = '' 
    if 'time_start' in request.values:
        data_start_time = request.values['time_start']

    data_end_time = ''
    if 'time_end' in request.values:
        data_end_time = request.values['time_end']

    box_directory = ''
    if 'box_directory' in request.values:
        box_directory = request.values['box_directory']

    # Get the object ID of the study, used in the pipeline
    query = Study.objects.filter(pk=study_id)
    if not query.exists():
        flash('Could not find study corresponding to study id {0}'.format(study_id), category='danger')
        return redirect('/data-pipeline/{:s}'.format(study_id))
        #return abort(404)
    object_id = query.get().object_id

    pipeline_region = os.getenv("pipeline_region", None)
    if not pipeline_region:
        pipeline_region = 'us-east-1'
        flash('Pipeline region not configured, choosing default ({})'.format(pipeline_region), category='info')
        # return redirect('/data-pipeline/{:s}'.format(study_id))

    error_sentry = make_error_sentry("data", tags={"pipeline_frequency": "manually"})
    # Get new data access credentials for the manual user, submit a manual job, display message
    # Report all errors to sentry including DataPipelineNotConfigured errors.
    with error_sentry:
        ssm_client = get_boto_client('ssm', pipeline_region)
        refresh_data_access_credentials('manually', ssm_client=ssm_client, webserver=True)
        batch_client = get_boto_client('batch', pipeline_region)
        for patient_id in participants:
            try:
                participant = Participant.objects.get(patient_id=patient_id)
            except Exception as e:
                flash(f'Could not find participant {patient_id} in the database {e}', category='info')
                continue

            if participant.device_id:

                query_filter={'study_id': study_id}

                if data_start_time:
                    query_filter.update({'time_bin__gte': dateutils.str_to_datetime(data_start_time)})

                if data_end_time:
                    query_filter.update({'time_bin__lte': dateutils.str_to_datetime(date_end_time)})

                print(f'excuting query {query_filter} to check that data exists before starting pipeline')

                if participant.chunk_registries.filter(**query_filter).count() > 0:
                    create_one_job('manually', object_id, session_researcher.username,
                            'run_pipeline',
                            destination_email_addresses=destination_email_addresses_string,
                            data_start_datetime=data_start_time,
                            data_end_datetime=data_end_time,
                            participants=patient_id,
                            job_type=job_type,
                            box_directory=box_directory,
                            webserver=True,
                            client=batch_client)

        flash('Data pipeline code successfully initiated!', 'success')
    

        if data_start_time and data_end_time:
            flash('Data pipeline successfully initiated on data collected between {0} and {1}! Email(s) will be sent to {2} on completion.'.format(data_start_time, data_end_time, destination_email_addresses), 'success')
        elif data_start_time:
            flash('Data pipeline successfully initiated on data collected after {0}! Email(s) will be sent to {1} on completion.'.format(data_start_time, destination_email_addresses), 'success')
        elif data_end_time:
            flash('Data pipeline successfully initiated on data collected before {0}! Email(s) will be sent to {1} on completion.'.format(data_start_time, destination_email_addresses), 'success')
        else: 
            flash('Data pipeline successfully initiated! Email(s) will be sent to {0} on completion.'.format(destination_email_addresses), 'success')
    if error_sentry.errors:
        flash('An unknown error occurred when trying to run this task.', category='danger')
        print(error_sentry)
    
    return redirect('/data-pipeline/{:s}'.format(study_id))

@data_pipeline_api.route('/terminate-pipeline/<string:study_id>', methods=['POST'])
@authenticate_researcher_study_access
def terminate_pipeline(study_id):
    """
    Terminate an AWS Batch job for the Study specified
    :param study_id: Primary key of a Study
    """

    username = session["admin_username"]

    pipeline_id = request.values['pipeline_id']
    flash('terminating pipeline {0}'.format(pipeline_id))

    error_sentry = make_error_sentry("data", tags={"pipeline_frequency": "terminate_job manually"})
    # Get new data access credentials for the manual user, submit a manual job, display message
    # Report all errors to sentry including DataPipelineNotConfigured errors.
    with error_sentry:
        batch_client = get_boto_client('batch', pipeline_region)
        terminate_job(pipeline_id, username, batch_client)

    if error_sentry.errors:
        flash('An error occurred when trying to terminate the pipeline {0}: {1}'.format(pipeline_id, error_sentry), category='danger')
        print(error_sentry)
    else: 
        flash('Pipeline {0} terminated.'.format(pipeline_id), 'success')

    return redirect('/data-pipeline/{:s}'.format(study_id))
