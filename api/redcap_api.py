import redcap
from flask import Blueprint, request, jsonify

from database.user_models import Participant
from database.userinfo_models import ParticipantInfo

redcap_api = Blueprint('redcap_api', __name__)


@redcap_api.route('/user/redcap', methods=['POST'])
def redcap_handler():
    record_id = request.form.get('record', '')
    if not record_id:
        return jsonify({'msg': 'Record not found.'}), 400

    try:
        API_Token = ''
        project = redcap.Project('', API_Token)
        records = project.export_records(records=[record_id])

        if not records:
            return jsonify({'msg': 'Record not found.'}), 400

        record = records[0]

        # Create user
        patient_id, password = Participant.create_with_password(study_id=1)
        patient = Participant.objects.get(patient_id__exact=patient_id)
        ParticipantInfo(user=patient, country='United States', zipcode='78731', timezone='UTC',
                        record_id=record_id).save()

        # Upload data back
        record['beiwe_username'] = patient_id
        record['beiwe_password'] = password
        response = project.import_records([record])
        if response['count'] != 1:
            return jsonify({'msg': 'Failed to update RedCap.'}), 400

        return jsonify({'msg': 'User created'}), 201
    except:
        return jsonify({'msg': 'Failed to create user'}), 400
