import base64
from collections import defaultdict
from datetime import datetime

# import fitbit
import requests
from flask import Blueprint, redirect, request, jsonify
from flask_jwt_extended import jwt_required, decode_token

from config.fitbit_constants import TIME_SERIES_TYPES
from config.settings import FITBIT_CLIENT_ID, FITBIT_CLIENT_SECRET
from database.fitbit_models import FitbitCredentials, FitbitRecord
from database.user_models import Participant

import libs.fitbit as fitbit

from pipeline.boto_helpers import get_boto_client

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
            record = FitbitCredentials(access_token=access_token, refresh_token=refresh_token, user=participant)
            record.save()
    except:
        pass
    

    try:
        fitbit.create_fitbit_records_trigger(record)
    except:
        pass

    return jsonify({'msg': 'Done.'}), 200

