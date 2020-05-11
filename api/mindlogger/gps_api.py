from datetime import datetime
from typing import List

from flask import Blueprint, jsonify, request, abort
from flask_jwt_extended import (
    jwt_required, get_jwt_identity
)

from database.gps_models import GPSMeasure
from database.user_models import Participant

gps_api = Blueprint('gps_api', __name__)


@gps_api.route('/gps', methods=['POST'])
@jwt_required
def add_gps_measure():
    if not request.is_json:
        return abort(400)

    patient_id = get_jwt_identity()
    try:
        user = Participant.objects.get(patient_id__exact=patient_id)
    except:
        return abort(400)

    data: List[dict] = request.json
    count = 0

    if not isinstance(data, list):
        return jsonify({'msg': 'Must be an array!'})

    for dp in data:
        if any([key not in dp for key in ['timestamp', 'distance', 'standard_deviation']]):
            continue
        try:
            timestamp = int(dp['timestamp'])
            distance = float(dp['distance'])
            standard_deviation = float(dp['standard_deviation'])
            updated_time = datetime.utcfromtimestamp(timestamp)
            if distance < 0:
                continue

            GPSMeasure(user=user, last_updated=updated_time, distance=distance,
                       standard_deviation=standard_deviation).save()
            count += 1
        except:
            pass

    return jsonify({'msg': '{}/{} has been saved.'.format(count, len(data))})
