from collections import defaultdict

from flask import Blueprint, jsonify
from flask_jwt_extended import (
    jwt_required, get_jwt_identity
)

from database.user_models import Participant

schedule_api = Blueprint('schedule_api', __name__)


@schedule_api.route('', methods=['GET'])
@jwt_required
def get_schedule():
    patient_id = get_jwt_identity()
    res = defaultdict(dict)
    try:
        applets = Participant.objects.get(patient_id__exact=patient_id).study.applets.all()
        for applet in applets:
            for activity in applet.activities.all():
                res['applet/' + str(applet.pk)]['activity/' + str(activity.pk)] = {
                    'lastResponse': None
                }
        return jsonify(res), 200
    except:
        return jsonify({}), 200
