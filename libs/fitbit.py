import os
import sys
import json
import base64
from collections import defaultdict
from datetime import datetime, date, timedelta
import requests
import traceback

import fitbit
from flask_jwt_extended import (create_access_token, decode_token, jwt_required)

# noinspection PyUnresolvedReferences
from config import load_django
from config.fitbit_constants import TIME_SERIES_TYPES, INTRA_TIME_SERIES_TYPES
from config.settings import (
    FITBIT_CLIENT_ID,
    FITBIT_CLIENT_SECRET,
    FITBIT_REDIRECT_URL,
    FITBIT_LAMBDA_ARN,
    IS_SERVERLESS
)

from database.fitbit_models import (FitbitRecord, FitbitIntradayRecord, FitbitCredentials)
from database.user_models import Participant

from pipeline.boto_helpers import get_boto_client


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

def create_fitbit_records_trigger(credential):
    client = get_boto_client('events', pipeline_region)

    rule_name = FITBIT_RECORDS_LAMBDA_RULE.format(credential.id)

    try:
        client.describe_rule(Name=rule_name)
        targets = client.list_targets_by_rule(Rule=rule_name)
        client.remove_targets(
            Rule=rule_name,
            Ids=[target['Id'] for target in targets['Targets']],
        )
        client.delete_rule(Name=rule_name)
    except Exception as e:
        pass

    client.put_rule(
        Name=rule_name,
        ScheduleExpression='rate(4 hours)',
        State='ENABLED'
    )

    client.put_targets(
        Rule=rule_name,
        Targets=[
            {
                'Arn': FITBIT_LAMBDA_ARN,
                'Id': 'fitbit_record_lambda',
                'Input': json.dumps({"credential": str(credential.id)})
            }
        ]
    )


def get_fitbit_record(access_token, refresh_token, base_date, end_date, update_cb, fetched_dates):
    res = {}

    client = fitbit.Fitbit(
        FITBIT_CLIENT_ID,
        FITBIT_CLIENT_SECRET,
        access_token=access_token,
        refresh_token=refresh_token,
        refresh_cb=update_cb
    )

    print(f"Fetching singular data")
    yield 'devices', client.get_devices()
    yield 'friends', client.get_friends()
    yield 'friends_leaderboard', client.get_friends_leaderboard()
    
    res = defaultdict(dict)
    for k, type_str in TIME_SERIES_TYPES.items():
        print(f"Fetching {k} time series")

        record = client.time_series(k, base_date=base_date, end_date=end_date)
        data = record[k.replace('/', '-')]
        for dp in data:
            date = dp['dateTime']
            res[date][k.replace('/', '_')] = dp['value']

    yield 'time_series', res


    delta = timedelta(days=1)
    intra_date = datetime.strptime(base_date, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    while intra_date <= end_date:
        intra_date_fmt = intra_date.strftime("%Y-%m-%d")

        if intra_date_fmt not in fetched_dates:
            print(f"Day: {intra_date_fmt}")

            res = defaultdict(dict)
            for k, type_str in INTRA_TIME_SERIES_TYPES.items():
        
                print(f"- fetching {k} intra-day time series")

                record = client.intraday_time_series(k, base_date=intra_date_fmt)

                k_db = k.replace('/', '_')
                k_api = k.replace('/', '-')
                data = record[f"{k_api}-intraday"]
                for metric in data['dataset']:
                    metric_datetime = f"{intra_date} {metric['time']}"
                    res[metric_datetime][k_db] = metric['value']

            yield 'intra_time_series', res

        intra_date += delta


def do_process_fitbit_records_lambda_handler(event, context):

    print(f"Received from lambda: {event}")

    credential_id = event['credential']
    credential = FitbitCredentials.objects.get(pk=credential_id)

    user = credential.user
    access_token = credential.access_token
    refresh_token = credential.refresh_token

    initial_date = '2020-05-01'
    final_date = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')

    print(f"Fetching dates for user {user.patient_id}")

    fetched_dates = set([
        d['last_updated'].strftime('%Y-%m-%d')
        for d in FitbitIntradayRecord.objects.filter(user=1).values('last_updated').values('last_updated')
    ])

    def update_token(token_dict):
        print("Updating token")
        credential.access_token = token_dict['access_token']
        credential.refresh_token = token_dict['refresh_token']
        credential.save()

    fixed_info = {}

    try:
        # There is a max time range
        for restype, res in get_fitbit_record(
            access_token, refresh_token,
            initial_date, final_date,
            update_token, fetched_dates
        ):
            if restype in ['devices', 'friends', 'friends_leaderboard']:
                fixed_info[restype] = res

            if restype == 'time_series':
                records = []
                for time, data in res.items():
                    records += [
                        FitbitRecord(user=user, last_updated=time, **fixed_info, **data)
                    ]
                FitbitRecord.objects.bulk_create(records)

            if restype == 'intra_time_series':
                records = []
                for time, data in res.items():
                    records += [
                        FitbitIntradayRecord(user=user, last_updated=time, **data)
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

        records = FitbitCredentials.objects.filter(user__patient_id__exact=patient_id)
        if records.exists():
            record: FitbitCredentials = records.get()
            record.access_token = access_token
            record.refresh_token = refresh_token
            record.save()
        else:
            record = FitbitCredentials(access_token=access_token, refresh_token=refresh_token, user=participant)
            record.save()
    except Exception as e:
        traceback.print_exc()
        raise Exception('INTERNAL_ERROR')

    try:
        client = get_boto_client('lambda', pipeline_region)
        client.invoke(
            FunctionName=FITBIT_LAMBDA_ARN,
            InvocationType='Event',
            Payload=json.dumps({"credential": str(record.id)})
        )
    except:
        traceback.print_exc()

    try:
        create_fitbit_records_trigger(record)
    except:
        traceback.print_exc()
