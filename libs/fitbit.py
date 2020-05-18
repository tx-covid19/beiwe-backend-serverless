import os
import sys
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
from config.settings import (FITBIT_CLIENT_ID, FITBIT_CLIENT_SECRET, FITBIT_REDIRECT_URL, IS_SERVERLESS)

from database.fitbit_models import (FitbitRecord, FitbitIntradayRecord, FitbitCredentials)
from database.user_models import Participant

from pipeline.boto_helpers import get_boto_client

FITBIT_RECORDS_LAMBDA_NAME = 'beiwe-fitbit-lambda'
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

    pipeline_region = os.getenv("pipeline_region", None)
    if not pipeline_region:
        pipeline_region = 'us-east-1'
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
    except client.exceptions.ResourceNotFoundException as e:
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
                'Arn': FITBIT_RECORDS_LAMBDA_NAME,
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

    intra_date = datetime.strptime(base_date, '%Y-%m-%d').date()

    try:
        # res['devices'] = client.get_devices()
        # res['friends'] = client.get_friends()
        # res['friends_leaderboard'] = client.get_friends_leaderboard()
        
        res['time_series'] = defaultdict(dict)
        res['intra_time_series'] = defaultdict(dict)

        for k, type_str in TIME_SERIES_TYPES.items():
            record = client.time_series(k, base_date=base_date, end_date=end_date)
            data = record[k.replace('/', '-')]
            for dp in data:
                date = dp['dateTime']
                res['time_series'][date][k.replace('/', '_')] = dp['value']

        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        for k, type_str in INTRA_TIME_SERIES_TYPES.items():
            delta = timedelta(days=1)
            intra_date = datetime.strptime(base_date, '%Y-%m-%d').date()
            while intra_date <= end_date:
                intra_date_fmt = intra_date.strftime("%Y-%m-%d")
                if intra_date_fmt in fetched_dates:
                    continue

                record = client.intraday_time_series(k, base_date=intra_date_fmt)

                k_db = k.replace('/', '_')
                k_api = k.replace('/', '-')
                data = record[f"{k_api}-intraday"]
                for metric in data['dataset']:
                    metric_datetime = f"{intra_date} {metric['time']}"
                    res['intra_time_series'][metric_datetime][k_db] = metric['value']
                intra_date += delta

    except:
        import traceback
        traceback.print_exc()
        
        return {}

    return res


def do_process_fitbit_records_lambda_handler(event, context):

    credential_id = event['credential']
    credential = FitbitCredentials.objects.get(pk=credential_id)

    fetched_dates = set([
        d['last_updated'].strftime('%Y-%m-%d')
        for d in FitbitIntradayRecord.objects.filter(user=1).values('last_updated').values('last_updated')
    ])

    def update_token(token_dict):
        credential.access_token = token_dict['access_token']
        credential.refresh_token = token_dict['refresh_token']
        credential.save()

    user = credential.user
    access_token = credential.access_token
    refresh_token = credential.refresh_token

    # There is a max time range
    res = get_fitbit_record(
        access_token, refresh_token,
        '2020-05-01', (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d'),
        update_token,
        fetched_dates
    )

    if 'time_series' in res:
        for time, data in res['time_series'].items():
            FitbitRecord(user=user, last_updated=time, devices=res['devices'], **data).save()

    if 'intra_time_series' in res:
        for time, data in res['intra_time_series'].items():
            FitbitIntradayRecord(user=user, last_updated=time, **data).save()

    return {
        'statusCode': 200,
        'body': 'Lambda finished!'
    }


def recreate_firbit_records_trigger():
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
        create_fitbit_records_trigger(record)
    except:
        pass
