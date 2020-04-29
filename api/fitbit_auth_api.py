import base64

import requests
from flask import Blueprint, redirect, request, jsonify
from flask_jwt_extended import jwt_required, decode_token, get_raw_jwt_header

from config.settings import FITBIT_CLIENT_ID, FITBIT_CLIENT_SECRET, FITBIT_REDIRECT_URL
from database.fitbit_models import FitbitRecord
from database.user_models import Participant

fitbit_auth_api = Blueprint('fitbit_auth_api', __name__)
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

@fitbit_auth_api.route('/request', methods=['GET'])
@jwt_required
def fitbit_request():
    jwt_str = request.headers.get('Authorization', '').split(' ')
    if len(jwt_str) != 2:
        return {'msg': 'Unauthorized.'}, 403
    jwt_token = jwt_str[1]
    return jsonify({
        'url': 'https://fitbit.com/oauth2/authorize?response_type=code&client_id={client_id}&scope={scope}&state={state}&redirect_uri={redirect_uri}'
            .format(
                client_id=FITBIT_CLIENT_ID,
                state=jwt_token,
                scope='%20'.join(SCOPES),
                redirect_uri=FITBIT_REDIRECT_URL,
            )
        }
    ), 200


def get_token():
    return base64.b64encode(
        "{}:{}".format(
            FITBIT_CLIENT_ID,
            FITBIT_CLIENT_SECRET
        ).encode('utf-8')).decode('utf-8')


@fitbit_auth_api.route('/authorize')
def fitbit_authorize():
    code = request.args.get('code', '')
    state = request.args.get('state', '')

    if not state:
        return jsonify({'msg': 'Unauthorized.'}), 403

    try:
        patient_id = decode_token(state)['identity']
        participant = Participant.objects.get(patient_id__exact=patient_id)
    except Exception as e:
        return jsonify({'msg': 'Unauthorized.'}), 403

    try:
        r = requests.post(
            'https://api.fitbit.com/oauth2/token',
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': 'Basic {}'.format(get_token()),
            },
            data={
                'client_id': FITBIT_CLIENT_ID,
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': FITBIT_REDIRECT_URL,
            },
            timeout=60
        )
        r.raise_for_status()
        resp = r.json()
        access_token = resp['access_token']
        refresh_token = resp['refresh_token']

        records = FitbitRecord.objects.filter(user__patient_id__exact=patient_id)
        if records.exists():
            # reauthorize, update existing results
            record: FitbitRecord = records.get()
            record.access_token = access_token
            record.refresh_token = refresh_token
            record.save()
        else:
            # new authorize
            FitbitRecord(access_token=access_token, refresh_token=refresh_token, user=participant).save()
    except Exception as e:
        print(e)
        return jsonify({'msg': 'Error.'}), 500

    return jsonify({'msg': 'Done.'}), 200
