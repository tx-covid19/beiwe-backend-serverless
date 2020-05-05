import base64
from collections import defaultdict
from datetime import datetime

import fitbit
import requests
from flask import Blueprint, redirect, request, jsonify
from flask_jwt_extended import jwt_required, decode_token

from config.fitbit_constants import TIME_SERIES_TYPES
from config.settings import FITBIT_CLIENT_ID, FITBIT_CLIENT_SECRET
from database.fitbit_models import FitbitCredentials, FitbitRecord
from database.user_models import Participant

fitbit_api = Blueprint('fitbit_api', __name__)
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


# TODO add Oauth2 PKEC

@fitbit_api.route('/request', methods=['GET'])
@jwt_required
def fitbit_request():
    jwt_str = request.headers.get('Authorization', '').split(' ')
    if len(jwt_str) != 2:
        return {'msg': 'Unauthorized.'}, 403
    jwt_token = jwt_str[1]
    return redirect('https://fitbit.com/oauth2/authorize'
                    '?response_type=code&client_id={client_id}&scope={scope}&state={state}'.format(
        client_id=FITBIT_CLIENT_ID, state=jwt_token, scope='%20'.join(SCOPES)))


def auth_url(code):
    return 'https://api.fitbit.com/oauth2/token?code={code}&client_id={client_id}&grant_type=authorization_code'.format(
        code=code,
        client_id=FITBIT_CLIENT_ID
    )


def get_token():
    return base64.b64encode(
        "{}:{}".format(
            FITBIT_CLIENT_ID,
            FITBIT_CLIENT_SECRET
        ).encode('utf-8')).decode('utf-8')


@fitbit_api.route('/authorize')
def fitbit_authorize():
    code = request.args.get('code', '')
    state = request.args.get('state', '')
    if not state:
        return jsonify({'msg': 'Unauthorized.'}), 403
    try:
        patient_id = decode_token(state)['identity']
        participant = Participant.objects.get(patient_id__exact=patient_id)
    except:
        return jsonify({'msg': 'Done.'}), 200

    try:
        r = requests.post(
            auth_url(code),
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': 'Basic {}'.format(get_token()),
            },
            timeout=60
        )
        r.raise_for_status()
        resp = r.json()
        access_token = resp['access_token']
        refresh_token = resp['refresh_token']

        records = FitbitCredentials.objects.filter(user__patient_id__exact=patient_id)
        if records.exists():
            # reauthorize, update existing results
            record: FitbitCredentials = records.get()
            record.access_token = access_token
            record.refresh_token = refresh_token
            record.save()
        else:
            # new authorize
            FitbitCredentials(access_token=access_token, refresh_token=refresh_token, user=participant).save()
    except:
        pass
    return jsonify({'msg': 'Done.'}), 200


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
        # These two APIs are broken
        # res['friends'] = client.get_friends()
        # res['friends_leaderboard'] = client.get_friends_leaderboard('30d')
        res['time_series'] = defaultdict(dict)

        for k, type_str in TIME_SERIES_TYPES.items():
            record = client.time_series(k, base_date=base_date, end_date=end_date)
            data = record[k.replace('/', '-')]
            for dp in data:
                date = dp['dateTime']
                res['time_series'][date][k.replace('/', '_')] = dp['value']
    except:
        # TODO log and retry
        return {}

    return res


# TODO: add authentication in production
@fitbit_api.route('/refresh')
def refresh_fitbit():
    for record in FitbitCredentials.objects.all():
        def update_token(token_dict):
            record.access_token = token_dict['access_token']
            record.refresh_token = token_dict['refresh_token']
            record.save()

        user = record.user
        access_token = record.access_token
        refresh_token = record.refresh_token

        # There is a max time range
        res = get_fitbit_record(access_token, refresh_token, '2020-04-01', datetime.utcnow().strftime('%Y-%m-%d'),
                                update_token)
        if 'time_series' in res:
            for time, data in res['time_series'].items():
                FitbitRecord(user=user, last_updated=time, devices=res['devices'], **data).save()

    return jsonify("updated"), 200
