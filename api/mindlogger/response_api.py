from django.db import transaction
from flask import Blueprint, jsonify, request, abort
from flask_jwt_extended import (
    jwt_required, get_jwt_identity
)
import json

from database.mindlogger_models import Screen, Response
from database.user_models import Participant

response_api = Blueprint('response_api', __name__)


@response_api.route('/last7Days/<applet_id>', methods=['GET'])
@jwt_required
def get_recent_response(applet_id):
    return jsonify({'responses': {}}), 200


@response_api.route('/<applet_id>/<activity_id>', methods=['POST'])
@jwt_required
def add_response(applet_id, activity_id):
    patient_id = get_jwt_identity()
    try:
        user = Participant.objects.get(patient_id__exact=patient_id)
    except:
        return abort(401)

    try:
        meta_data = request.form.get('metadata')
        data = json.loads(meta_data)
        resp: dict = data['responses']
    except:
        return abort(400)

    try:
        with transaction.atomic():
            for key, value in resp.items():
                screen = Screen.objects.get(URI__exact=key, activity__pk=activity_id, activity__applet__pk=applet_id)
                Response(user=user, screen=screen, value=json.dumps(value)).save()
        return jsonify({}), 200
    except:
        return abort(400)
