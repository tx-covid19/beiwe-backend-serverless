from django.core.exceptions import ObjectDoesNotExist
from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from database.serializers.tracker import TrackerRecordSerializer
from database.tracker_models import TrackRecord
from database.user_models import Participant

tracker_api = Blueprint('tracker_api', __name__)


@tracker_api.route('/user/tracker', methods=['GET', 'POST'])
@jwt_required
def tracker_handler():
    patient_id = get_jwt_identity()
    if request.method == 'GET':
        records = TrackRecord.get_with_timezone(patient_id)
        serializer = TrackerRecordSerializer(records, many=True)
        import sys
        print(serializer.data, file=sys.stderr)
        return jsonify(serializer.data)
    elif request.method == 'POST':
        try:
            user = Participant.objects.get(patient_id__exact=patient_id)
        except ObjectDoesNotExist:
            return jsonify({'msg': 'User not found.'}), 404
        serializer = TrackerRecordSerializer(data=request.json)
        if serializer.is_valid():
            record = TrackRecord(user=user, **request.json)
            record.save()
            return jsonify(serializer.data), 201
        return jsonify({'msg': serializer.errors}), 400
