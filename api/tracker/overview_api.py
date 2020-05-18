from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from database.info_models import Pollen, Weather
from database.serializers.info import WeatherSerializer, PollenSerializer
from database.serializers.tracker import TrackerRecordSerializer
from database.tracker_models import TrackRecord, ParticipantInfo

overview_api = Blueprint('overview_api', __name__)


@overview_api.route('/overview', methods=['GET'])
@jwt_required
def overview_handler():
    patient_id = get_jwt_identity()

    records = TrackerRecordSerializer(TrackRecord.objects.filter(user__patient_id=patient_id), many=True).data
    pollen = {}
    weather = {}

    info_set = ParticipantInfo.objects.filter(user__patient_id__exact=patient_id)
    if info_set.exists():
        info: ParticipantInfo = info_set.get()
        country = info.country
        zipcode = info.zipcode

        pollen = PollenSerializer(Pollen.latest_record(country, zipcode)).data
        weather = WeatherSerializer(Weather.latest_record(country, zipcode)).data

    return jsonify({
        'tracker': records,
        'pollen': {
            **pollen
        },
        'weather': {
            **weather
        }
    }), 200
