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
    res = {}
    return {'applet/5':
                {'activity/3':
                     {'lastResponse': '2020-05-06T19:46:12.056000-05:00'}
                 }
            }

    # try:
    #     for applet in Participant.objects.get(patient_id__exact=patient_id).study.applets.all():
    #         res['applet/' + str(applet.pk)] = {'1': '2'}
    #     return jsonify(res), 200
    # except:
    #     return jsonify(res), 200
