import redcap
from flask import Blueprint, request, jsonify

from config.settings import REDCAP_SERVER_URL, REDCAP_API_TOKEN
from database.redcap_models import RedcapRecord
from database.user_models import Participant

redcap_api = Blueprint('redcap_api', __name__)


@redcap_api.route('/user/redcap/<study_id>', methods=['POST'])
def redcap_handler(study_id):
    record_id = request.form.get('record', '')
    if not record_id:
        return jsonify({'msg': 'Missing record information'}), 400

    if RedcapRecord.objects.filter(record_id__exact=record_id).exists():
        return jsonify({'msg': 'User exists'}), 304

    # create beiwe user and write credentials back to Redcap
    try:
        project = redcap.Project(REDCAP_SERVER_URL, REDCAP_API_TOKEN)
        records = project.export_records(records=[record_id])

        if not records:
            return jsonify({'msg': 'Records not found.'}), 400

        record = records[0]

        # Create user
        patient_id, password = Participant.create_with_password(study_id=study_id)
        patient = Participant.objects.get(patient_id__exact=patient_id)
        RedcapRecord(user=patient, record_id=record_id).save()

        # Upload data back
        record['beiwe_username'] = patient_id
        record['beiwe_password'] = password
        response = project.import_records([record])
        if response['count'] != 1:
            return jsonify({'msg': 'Failed to update RedCap.'}), 304

        return jsonify({'msg': 'User created'}), 201
    except:
        return jsonify({'msg': 'Failed to create user'}), 400
