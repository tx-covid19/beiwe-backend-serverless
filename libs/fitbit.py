import os
import sys
import json
import base64
from collections import defaultdict
from datetime import datetime, date, timedelta
import requests
import traceback

import boto3
import fitbit
from flask_jwt_extended import (create_access_token, decode_token)

from config import load_django
from config.fitbit_constants import TIME_SERIES_TYPES, INTRA_TIME_SERIES_TYPES
from config.settings import (
    FITBIT_CLIENT_ID,
    FITBIT_CLIENT_SECRET,
    FITBIT_REDIRECT_URL,
    FITBIT_LAMBDA_ARN,
    IS_SERVERLESS
)

from database.fitbit_models import (
    FitbitInfo,
    FitbitRecord,
    FitbitIntradayRecord,
    FitbitCredentials
)
from database.user_models import Participant


pipeline_region = os.getenv("pipeline_region", None)
if not pipeline_region:
    pipeline_region = 'us-east-1'

FITBIT_RECORDS_LAMBDA_RULE = 'beiwe-fitbit-{}-lambda'

SCOPES = [
    'profile',
    'activity',
    'heartrate',
    'location',
    'nutrition',
    'settings',
    'sleep',
    'social',
    'weight'
]


def delete_fitbit_records_trigger(credential):
    events_client = boto3.client('events', region_name=pipeline_region)
    lambda_client = boto3.client('lambda', region_name=pipeline_region)

    rule_name = FITBIT_RECORDS_LAMBDA_RULE.format(credential.id)
    permission_name = f"{rule_name}-event"

    events_client.describe_rule(Name=rule_name)
    targets = events_client.list_targets_by_rule(Rule=rule_name)
    events_client.remove_targets(
        Rule=rule_name,
        Ids=[target['Id'] for target in targets['Targets']],
    )
    events_client.delete_rule(Name=rule_name)
    lambda_client.remove_permission(
        FunctionName=FITBIT_LAMBDA_ARN,
        StatementId=permission_name,
    )


def create_fitbit_records_trigger(credential):
    events_client = boto3.client('events', region_name=pipeline_region)
    lambda_client = boto3.client('lambda', region_name=pipeline_region)

    rule_name = FITBIT_RECORDS_LAMBDA_RULE.format(credential.id)
    permission_name = f"{rule_name}-event"

    try:
        delete_fitbit_records_trigger(credential)
    except Exception as e:
        pass

    rule = events_client.put_rule(
        Name=rule_name,
        ScheduleExpression='cron(0 1 * * ? *)',
        State='ENABLED'
    )

    events_client.put_targets(
        Rule=rule_name,
        Targets=[
            {
                'Arn': FITBIT_LAMBDA_ARN,
                'Id': 'fitbit_record_lambda',
                'Input': json.dumps({"credential": str(credential.id)})
            }
        ]
    )

    lambda_client.add_permission(
        FunctionName=FITBIT_LAMBDA_ARN,
        StatementId=permission_name,
        Action="lambda:InvokeFunction",
        Principal="events.amazonaws.com",
        SourceArn=rule['RuleArn'],
    )


def get_fitbit_client(credential, update_cb=None):
    return fitbit.Fitbit(
        FITBIT_CLIENT_ID,
        FITBIT_CLIENT_SECRET,
        access_token=credential.access_token,
        refresh_token=credential.refresh_token,
        refresh_cb=update_cb
    )


def get_fitbit_record(credential, base_date, end_date, update_cb=None, fetched_dates=[], info=True, interday=True, intraday=True):

    fitbit_client = get_fitbit_client(credential, update_cb)

    if info:
        print(f"Fetching singular data")

        info_data = {}

        info_data['devices'] = fitbit_client.get_devices()

        friends = fitbit_client.get_friends()
        if 'data' in friends:
            friends = friends['data']
            for friend in friends:
                if 'attributes' in friend:
                    attributes = friend['attributes']
                    if 'avatar' in attributes:
                        del friend['attributes']['avatar']
                    friend.update(attributes)
                    del friend['attributes']
        else:
            friends = []
        info_data['friends'] = friends

        leaderboard = fitbit_client.get_friends_leaderboard()
        if 'data' in leaderboard:
            leaderboard = leaderboard['data']
            for friend in leaderboard:
                if 'relationships' in friend:
                    del friend['relationships']

                if 'attributes' in friend:
                    attributes = friend['attributes']
                    friend.update(attributes)
                    del friend['attributes']
        else:
            leaderboard = []
        info_data['friends_leaderboard'] = leaderboard

        yield 'info', info_data
        del info_data

    BMR = {}

    if interday:

        res = defaultdict(dict)
        for data_stream, _ in TIME_SERIES_TYPES.items():
            print(f"Fetching {data_stream} time series")

            record = fitbit_client.time_series(
                data_stream,
                base_date=base_date,
                end_date=end_date
            )
            data = record[data_stream.replace('/', '-')]
            for dp in data:
                if data_stream == 'sleep':
                    date = dp['dateOfSleep']
                    if date in fetched_dates:
                        continue
                    res[date][data_stream] = \
                        res[date].get(data_stream, []) + [dp]
                else:
                    date = dp['dateTime']
                    if date in fetched_dates:
                        continue
                    res[date][data_stream.replace('/', '_')] = dp['value']

                if data_stream == 'activities/caloriesBMR':
                    minute_BMR = float(dp['value']) / 24. / 60.
                    BMR[date] = minute_BMR + 0.005  # corretion for daily spec

        yield 'time_series', res

    if intraday:

        delta = timedelta(days=1)
        intra_date = datetime.strptime(base_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        while intra_date <= end_date:
            intra_date_fmt = intra_date.strftime("%Y-%m-%d")

            if intra_date_fmt not in fetched_dates:
                print(f"Day: {intra_date_fmt}")

                res = defaultdict(dict)
                for data_stream, data_stream_config in INTRA_TIME_SERIES_TYPES.items():

                    print(f"- fetching {data_stream} intra-day time series")

                    record = fitbit_client.intraday_time_series(
                        data_stream,
                        base_date=intra_date_fmt,
                        detail_level=data_stream_config['interval']
                    )

                    data_stream_db = data_stream.replace('/', '_')
                    data_stream_api = data_stream.replace('/', '-')
                    data = record[f"{data_stream_api}-intraday"]
                    for metric in data['dataset']:

                        threshold = 0.0
                        if data_stream == 'activities/calories':
                            threshold = BMR.get(intra_date, 0.0)

                        if metric['value'] > threshold:
                            metric_datetime = f"{intra_date} {metric['time']}"
                            res[metric_datetime][data_stream_db] = metric['value']

                yield 'intra_time_series', res

            intra_date += delta


def do_process_fitbit_records_lambda_handler(event, context):

    print(f"Received from lambda: {event}")

    credential_id = event['credential']
    credential = FitbitCredentials.objects.get(pk=credential_id)

    participant = credential.participant
    access_token = credential.access_token
    refresh_token = credential.refresh_token

    initial_date = '2020-05-01'
    yesterday_date = (
        datetime.utcnow() - timedelta(days=1)
    ).strftime('%Y-%m-%d')

    print(f"Fetching dates for participant {participant.patient_id}")

    fetched_dates = set([
        record['date'].strftime('%Y-%m-%d')
        for record in FitbitRecord.objects.filter(participant=participant).values('date').values('date')
    ])

    def update_token(token_dict):
        print("Updating token")
        credential.access_token = token_dict['access_token']
        credential.refresh_token = token_dict['refresh_token']
        credential.save()

    try:
        for resource_type, resource in get_fitbit_record(
            credential,
            initial_date, yesterday_date,
            update_token, fetched_dates,
        ):
            if resource_type == 'info':
                FitbitInfo(
                    participant=participant,
                    date=datetime.utcnow(),
                    **resource
                ).save()

            if resource_type == 'time_series':
                records = []
                for time, data in resource.items():
                    records += [
                        FitbitRecord(
                            participant=participant,
                            date=time + ' 00:00:00+00:00',
                            **data
                        )
                    ]
                FitbitRecord.objects.bulk_create(records)

            if resource_type == 'intra_time_series':
                records = []
                for time, data in resource.items():
                    records += [
                        FitbitIntradayRecord(
                            participant=participant,
                            date=time + '+00:00',
                            **data
                        )
                    ]
                FitbitIntradayRecord.objects.bulk_create(records)

    except Exception as e:
        traceback.print_exc()

        return {
            'statusCode': 500,
            'body': str(e)
        }
    else:
        return {
            'statusCode': 200,
            'body': 'Lambda finished!'
        }


def recreate_fitbit_records_trigger():
    for credential in FitbitCredentials.objects.all():
        create_fitbit_records_trigger(credential)


def get_client_token():
    return base64.b64encode(
        "{}:{}".format(
            FITBIT_CLIENT_ID,
            FITBIT_CLIENT_SECRET
        ).encode('utf-8')).decode('utf-8')


def redirect(patient_id):

    access_token = create_access_token(patient_id)

    url = 'https://fitbit.com/oauth2/authorize?response_type=code&client_id={client_id}&scope={scope}&state={state}&redirect_uri={redirect_uri}' \
        .format(
            client_id=FITBIT_CLIENT_ID,
            state=access_token,
            scope='%20'.join(SCOPES),
            redirect_uri=FITBIT_REDIRECT_URL,
        )

    return url


def authorize(code, state):
    try:
        patient_id = decode_token(state)['identity']
        participant = Participant.objects.get(patient_id__exact=patient_id)
    except:
        raise Exception('INVALID_USER')

    try:
        r = requests.post(
            'https://api.fitbit.com/oauth2/token?code={code}&client_id={client_id}&redirect_uri={url}&grant_type=authorization_code'.format(
                code=code,
                client_id=FITBIT_CLIENT_ID,
                url=FITBIT_REDIRECT_URL,
            ),
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': 'Basic {}'.format(get_client_token()),
            },
            timeout=60
        )

        resp = r.json()
        access_token = resp['access_token']
        refresh_token = resp['refresh_token']

        records = FitbitCredentials.objects.filter(
            participant__patient_id__exact=patient_id
        )
        if records.exists():
            record = records.get()
            record.access_token = access_token
            record.refresh_token = refresh_token
            record.save()
        else:
            record = FitbitCredentials(
                access_token=access_token,
                refresh_token=refresh_token,
                participant=participant
            )
            record.save()
    except Exception as e:
        traceback.print_exc()
        raise Exception('INTERNAL_ERROR')

    # try:
    #     client = get_boto_client('lambda', pipeline_region)
    #     client.invoke(
    #         FunctionName=FITBIT_LAMBDA_ARN,
    #         InvocationType='Event',
    #         Payload=json.dumps({"credential": str(record.id)})
    #     )
    # except:
    #     traceback.print_exc()

    try:
        create_fitbit_records_trigger(record)
    except:
        traceback.print_exc()
