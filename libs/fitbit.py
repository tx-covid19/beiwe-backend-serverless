import os
import sys
from collections import defaultdict
from datetime import datetime

# noinspection PyUnresolvedReferences
from config import load_django
from config.fitbit_constants import TIME_SERIES_TYPES
from config.settings import (FITBIT_CLIENT_ID, FITBIT_CLIENT_SECRET, IS_SERVERLESS)


FITBIT_RECORDS_LAMBDA_NAME = 'beiwe-fitbit-lambda'
FITBIT_RECORDS_LAMBDA_RULE = 'beiwe-fitbit-{}-lambda'


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
                'Input': '{"credential": "{}"}'.format(credential.id)
            }
        ]
    )


def get_fitbit_record(access_token, refresh_token, base_date, end_date, update_cb):
    res = {}

    client = fitbit.Fitbit(
        FITBIT_CLIENT_ID,
        FITBIT_CLIENT_SECRET,
        access_token=access_token,
        refresh_token=refresh_token,
        refresh_cb=update_cb
    )

    try:
        res['devices'] = client.get_devices()
        res['friends'] = client.get_friends()
        res['friends_leaderboard'] = client.get_friends_leaderboard('30d')
        res['time_series'] = defaultdict(dict)

        for k, type_str in TIME_SERIES_TYPES.items():
            record = client.time_series(k, base_date=base_date, end_date=end_date)
            data = record[k.replace('/', '-')]
            for dp in data:
                date = dp['dateTime']
                res['time_series'][date][k.replace('/', '_')] = dp['value']
    except:
        return {}

    return res


def do_process_fitbit_records_lambda_handler(event, context):

    credential_id = event['credential']
    credential = FitbitCredentials.objects.get(pk=credential_id)

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
        '2020-04-01', datetime.utcnow().strftime('%Y-%m-%d'),
        update_token
    )

    if 'time_series' in res:
        for time, data in res['time_series'].items():
            FitbitRecord(user=user, last_updated=time, devices=res['devices'], **data).save()

    return {
        'statusCode': 200,
        'body': 'Lambda finished!'
    }


def recreate_firbit_records_trigger():
    for credential in FitbitCredentials.objects.all():
        create_fitbit_records_trigger(credential)