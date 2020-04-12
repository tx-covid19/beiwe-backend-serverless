from django.core.exceptions import ObjectDoesNotExist
from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from database.event_models import Event
from database.serializers.event import EventSerializer
from database.user_models import Participant

event_api = Blueprint('event_api', __name__)


@event_api.route('/user/event', methods=['POST'])
@jwt_required
def event_handler():
    patient_id = get_jwt_identity()
    try:
        user = Participant.objects.get(patient_id__exact=patient_id)
    except ObjectDoesNotExist:
        return jsonify({'msg': 'User not found.'}), 404

    serializer = EventSerializer(data=request.json)
    if serializer.is_valid():
        record = Event(user=user, **request.json)
        record.save()
        return jsonify(serializer.data), 201
    return jsonify({'msg': serializer.errors}), 400
