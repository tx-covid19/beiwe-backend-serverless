from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    jwt_required, get_jwt_identity
)

from database.gps_models import GPSMeasure
from database.user_models import Participant

gps_api = Blueprint('gps_api', __name__)


# {
#     "duration": 3600008,
#     "end_time": 1589227819,
#     "distance": 123.34,
#     "standard_deviation": 6.1,
#     "n": 7
# }
@gps_api.route('/gps', methods=['POST'])
@jwt_required
def add_gps_measure():
    if not request.is_json:
        return jsonify({'msg': 'Must be a json body.'}), 400

    patient_id = get_jwt_identity()
    try:
        user = Participant.objects.get(patient_id__exact=patient_id)
    except:
        return jsonify({'msg': 'No access'}), 401

    data = request.json
    try:
        timestamp = int(data['end_time'])
        distance = float(data['distance'])
        standard_deviation = float(data['standard_deviation'])
        count = int(data['n'])
        duration = int(data['duration'])
        if duration < 0 or count < 0 or distance < 0:
            return jsonify({'msg': 'Bad data.'}), 400

        updated_time = datetime.utcfromtimestamp(timestamp)
        GPSMeasure(user=user, last_updated=updated_time, n=count, duration=duration, distance=distance,
                   standard_deviation=standard_deviation).save()
        return jsonify({'msg': 'GPS updated.'}), 200
    except:
        return jsonify({'msg': 'Bad data.'}), 400
