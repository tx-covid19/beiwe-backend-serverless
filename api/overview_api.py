from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from database.info_models import CovidCase, Pollen, Weather
from database.serializers.info import CovidCaseSerializer, WeatherSerializer, PollenSerializer
from database.serializers.tracker import TrackerRecordSerializer
from database.tracker_models import TrackRecord
from database.userinfo_models import ParticipantInfo

overview_api = Blueprint('overview_api', __name__)


@overview_api.route('/user/overview', methods=['GET'])
@jwt_required
def overview_handler():
    patient_id = get_jwt_identity()

    records = TrackerRecordSerializer(TrackRecord.objects.filter(user__patient_id=patient_id), many=True).data

    covid_cases = {}
    pollen = {}
    weather = {}

    country, zipcode = ParticipantInfo.get_country_zipcode(patient_id)

    if country and zipcode:
        covid_cases = CovidCaseSerializer(CovidCase.latest_record(country, zipcode)).data
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
        }
    }), 200
