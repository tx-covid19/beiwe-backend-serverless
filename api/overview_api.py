import sys

# import fitbit
# from fitbit.exceptions import BadResponse
from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from config.settings import FITBIT_CLIENT_ID, FITBIT_CLIENT_SECRET
from database.fitbit_models import FitbitRecord
from database.info_models import CovidCase, Pollen, Weather
from database.serializers.info import CovidCaseSerializer, WeatherSerializer, PollenSerializer
from database.serializers.tracker import TrackerRecordSerializer
from database.tracker_models import TrackRecord
from database.userinfo_models import ParticipantInfo

overview_api = Blueprint('overview_api', __name__)


def get_fitbit_info(patient_id):
    records = FitbitRecord.objects.filter(user__patient_id__exact=patient_id)
    if records.exists():
        record: FitbitRecord = records.get()

        def update_token(token_dict):
            record.access_token = token_dict['access_token']
            record.refresh_token = token_dict['refresh_token']
            record.save()

        client = fitbit.Fitbit(
            FITBIT_CLIENT_ID,
            FITBIT_CLIENT_SECRET,
            access_token=record.access_token,
            refresh_token=record.refresh_token,
            refresh_cb=update_token
        )
        try:
            # TODO data processing
            profile_response = client.user_profile_get()
            body_resp = client.activities_list()
            return {
                'user': profile_response['user'],
                'body': body_resp
            }
        except BadResponse:
            print(BadResponse, file=sys.stderr)
    else:
        return {}


@overview_api.route('/overview', methods=['GET'])
@jwt_required
def overview_handler():
    patient_id = get_jwt_identity()

    records = TrackerRecordSerializer(TrackRecord.objects.filter(user__patient_id=patient_id), many=True).data
    covid_cases = {}
    pollen = {}
    weather = {}

    info_set = ParticipantInfo.objects.filter(user__patient_id__exact=patient_id)
    if info_set.exists():
        info: ParticipantInfo = info_set.get()
        country = info.country
        state = info.state
        zipcode = info.zipcode

        covid_cases = CovidCaseSerializer(CovidCase.latest_record(country, state, zipcode)).data
        pollen = PollenSerializer(Pollen.latest_record(country, zipcode)).data
        weather = WeatherSerializer(Weather.latest_record(country, zipcode)).data

    return jsonify({
        'tracker': records,
        'covid_cases': {
            **covid_cases,
        },
        'pollen': {
            **pollen
        },
        'weather': {
            **weather
        },
        'fitbit': {
            **get_fitbit_info(patient_id)
        }
    }), 200
