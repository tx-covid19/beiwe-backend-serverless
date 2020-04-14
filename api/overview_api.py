import requests
from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from database.info_models import CovidCase
from database.serializers.info import CovidCaseSerializer
from database.serializers.tracker import TrackerRecordSerializer
from database.tracker_models import TrackRecord
from database.userinfo_models import ParticipantInfo

overview_api = Blueprint('overview_api', __name__)


def get_pollen_data(zipcode):
    headers = {
        "Content-Type": "application/json",
        "Referer": "https://www.pollen.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) "
                      + "AppleWebKit/537.36 (KHTML, like Gecko) "
                      + "Chrome/65.0.3325.181 Safari/537.36"
    }
    try:
        r = requests.get(f'https://www.pollen.com/api/forecast/current/pollen/{zipcode}', headers=headers, timeout=30)
        data = r.json()
        forecast_date = data['ForecastDate']
        today_data = data['Location']['periods'][1]
        today_index = today_data['Index']
        today_pollens = [trigger['Name'] for trigger in today_data['Triggers']]
        return {
            'forecast_date': forecast_date,
            'index': today_index,
            'pollens': today_pollens
        }
    except Exception:
        return {}


@overview_api.route('/user/overview', methods=['GET'])
@jwt_required
def overview_handler():
    patient_id = get_jwt_identity()

    records = TrackerRecordSerializer(TrackRecord.objects.filter(user__patient_id=patient_id), many=True).data

    try:
        covid_cases = {
            **CovidCaseSerializer(CovidCase.objects.latest('timestamp')).data
        }
    except Exception:
        covid_cases = {}

    zipcode = ParticipantInfo.get_zipcode(patient_id)

    return jsonify({
        'tracker': records,
        'covid_cases': {
            **covid_cases,
        },
        'pollen': {
            **get_pollen_data(zipcode)
        }
    }), 200
