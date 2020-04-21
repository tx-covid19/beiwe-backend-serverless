from config.constants import ResearcherRole, ALL_JOB_TYPES
from config.settings import DOMAIN_NAME
from database.study_models import Study
from database.user_models import Researcher, StudyRelation
from database.pipeline_models import PipelineExecutionTracking

# This component of pipeline is part of the Beiwe server, the correct import is 'from pipeline.xyz...'
from pipeline.boto_helpers import get_boto_client
from pipeline.configuration_getters import get_eb_config, get_generic_config

from config.constants import API_TIME_FORMAT
import datetime
import os


def str_to_datetime(time_string):
    """ Translates a time string to a datetime object, raises a 400 if the format is wrong."""
    try:
        return datetime.datetime.strptime(time_string, API_TIME_FORMAT)
    except ValueError as e:
        if "does not match format" in e.message:
            return abort(400)


def refresh_data_access_credentials(freq, ssm_client=None, webserver=False):
    """
    Refresh the data access credentials for a particular BATCH USER user and upload them
    (encrypted) to the AWS Parameter Store. This enables AWS batch jobs to get the
    credentials and thereby access the data access API (DAA).
    This is used to know what call the data access credentials on AWS.

    :param freq: string, one of 'hourly' | 'daily' | 'weekly' | 'monthly' | 'manually'
    :param ssm_client: optional, ssm_client to use if one is already available
    :param webserver: whether or not the method is called from the webserver as opposed to API
    :return:
    """

    # Get or create Researcher with no password. This means that nobody can log in as this
    # Researcher in the web interface.
    researcher_name = 'BATCH USER {}'.format(freq)
    mock_researchers = Researcher.objects.filter(username=researcher_name)
    if not mock_researchers.exists():
        mock_researcher = Researcher.create_without_password(researcher_name)
    else:
        mock_researcher = mock_researchers.get()
        mock_researcher.save()

    # Ensure that the Researcher is attached to all Studies. This allows them to access all
    # data via the DAA.
    # is_batch_user=True,
    for study in Study.objects.all():
        StudyRelation.objects.get_or_create(
            study=study,
            researcher=mock_researcher,
            relationship=ResearcherRole.researcher,
        )
    
    # Reset the credentials. This ensures that they aren't stale.
    access_key, secret_key = mock_researcher.reset_access_credentials()

    if not webserver:
        generic_config = get_generic_config()
    else:
        generic_config = get_eb_config()

    # Append the frequency to the SSM (AWS Systems Manager) names. This ensures that the
    # different frequency jobs' keys do not overwrite each other.
    access_key_ssm_name = '{}-{}'.format(generic_config['access_key_ssm_name'], freq)
    secret_key_ssm_name = '{}-{}'.format(generic_config['secret_key_ssm_name'], freq)

    # Put the credentials (encrypted) into AWS Parameter Store
    if not ssm_client:
        ssm_client = get_boto_client('ssm')
    ssm_client.put_parameter(
        Name=access_key_ssm_name,
        Value=access_key,
        Type='SecureString',
        Overwrite=True,
    )
    ssm_client.put_parameter(
        Name=secret_key_ssm_name,
        Value=secret_key,
        Type='SecureString',
        Overwrite=True,
    )


def create_one_job(freq, object_id, owner_id, pipeline_function, destination_email_addresses='', data_start_datetime='',
                   data_end_datetime='', participants='', job_type='run_pipeline', box_directory='',
                   datastreams='', client=None, webserver=False):
    """
    Create an AWS batch job
    The aws_object_names and client parameters are optional. They are provided in case
    that this function is run as part of a loop, to avoid an unnecessarily large number of
    file operations or API calls.

    config needs are the following: job_name, job_defn_name, queue_name

    :param freq: string e.g. 'daily', 'manually'
    :param object_id: a Study database object
    :param owner_id: a string, the username for the researcher executing the pipeline job
    :param pipeline_function: string containing the name of the pipeline function to execute
    :param destination_email_addresses: email address where status updates should be sent, optional
    :param data_start_datetime: start time for data query, optional
    :param data_end_datetime:  end time for data query, optional
    :param participants: comma separated string of patient_ids for participants whose data should be processed
    :param job_type: copy_to_box or run_pipeline, what are we doing?
    :param box_directory: directory on box to copy data into
    :param datastreams: the datastreams to perform the submitted operation on
    :param client: a credentialed boto3 client or None
    :param webserver: whether or not this was called from the webserver as opposed to a API
    :return:
    """

    # Get the AWS parameters and client if not provided
    if not webserver:
        aws_object_names = get_generic_config()
    else:
        aws_object_names = get_eb_config()

    # requires region_name be defined.
    if client is None:
        client = get_boto_client('batch', os.getenv("pipeline_region", None))

    # clean up list of participants
    if isinstance(participants, list):
        participants = " ".join(participants)
    elif ',' in participants:
        participants = " ".join(participants.split(','))

    # clean up the list of datastreams
    if isinstance(datastreams, list):
        datastreams = " ".join(datastreams)
    elif ',' in datastreams:
        datastreams = " ".join(datastreams.split(','))

    # clean up list of destination email addresses
    if isinstance(destination_email_addresses, list):
        destination_email_addresses = " ".join(destination_email_addresses)
    elif ',' in destination_email_addresses:
        destination_email_addresses = " ".join(destination_email_addresses.split(','))

    if job_type not in ALL_JOB_TYPES:
        raise ValueError(f"unknown job type {job_type}")

    request_datetime = datetime.datetime.now()

    print(f"scheduling {job_type} job for study {Study.objects.get(object_id=object_id).id}")
    pipeline_id = PipelineExecutionTracking.pipeline_scheduled(owner_id,
                                                               Study.objects.get(object_id=object_id).id,
                                                               request_datetime,
                                                               destination_email_addresses,
                                                               data_start_datetime,
                                                               data_end_datetime,
                                                               participants=participants,
                                                               job_type=job_type,
                                                               box_directory=box_directory)

    try:
        response = client.submit_job(
            jobName=aws_object_names['job_name'].format(freq=freq),
            jobDefinition=aws_object_names['job_defn_name'],
            jobQueue=aws_object_names['queue_name'],
            containerOverrides={
                'environment': [
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
                        'value': destination_email_addresses,
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
                        'value': participants,
                    },
                    {
                        'name': 'datastreams',
                        'value': datastreams,
                    },
                    {
                        'name': 'box_directory',
                        'value': box_directory,
                    }
                ]
            },
        )

    except Exception as e:
        PipelineExecutionTracking.pipeline_crashed(pipeline_id, datetime.datetime.now(), str(e))
        raise

    if response and 'jobId' in response:
        PipelineExecutionTracking.pipeline_set_batch_job_id(pipeline_id, response['jobId'])

    return


# TODO: these are not currently used at all except in a cron job.  Pipeline is being converted (for now)
# to be per-patient, not per-study.  The reason for this is because there is too much data
# to download per study, and the concept of calling different code for monthly, weekly etc.
# appears to have been discarded.  Currently only manual runs work.

# def create_all_jobs(freq):
#     """
#     Create one AWS batch job for each Study object
#     :param freq: string e.g. 'daily', 'monthly'
#     """
#
#     # TODO: Boto3 version 1.4.8 has AWS Batch Array Jobs, which are extremely useful for the
#     # task this function performs. We should switch to using them.
#
#     # Get new data access credentials for the user
#     # aws_object_names = get_aws_object_names()
#     refresh_data_access_credentials(freq)
#
#     # TODO: If there are issues with servers not getting spun up in time, make this a
#     # ThreadPool with random spacing over the course of 5-10 minutes.
#     error_sentry = make_error_sentry("data", tags={"pipeline_frequency": freq})
#     for study in Study.objects.filter(deleted=False):
#         with error_sentry:
#             # For each study, create a job
#             object_id = study.object_id
#             create_one_job(freq, object_id)


def hourly():
    pass
    # create_all_jobs('hourly')


def daily():
    pass
    # create_all_jobs('daily')


def weekly():
    pass
    # create_all_jobs('weekly')


def monthly():
    create_all_jobs('monthly')


def terminate_job(pipeline_id, user_id, client=None):

    # requires region_name be defined.
    if client is None:
        client = get_boto_client('batch')

    pipeline = PipelineExecutionTracking.objects.get(id=pipeline_id)

    if not pipeline.batch_job_id:
        raise ValueError(f'Error terminating pipeline {pipeline_id}, batch job id not found')

    client.terminate_job(jobId=pipeline.batch_job_id, reason=f'Terminated by user {user_id}')

    pipeline.terminate_job(pipeline_id, datetime.datetime.now(), reason=f'Terminated by user {user_id}')

    return
