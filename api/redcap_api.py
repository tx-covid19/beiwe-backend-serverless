import redcap
import requests
from flask import Blueprint, request, jsonify

from database.user_models import Participant
from database.userinfo_models import ParticipantInfo

redcap_api = Blueprint('redcap_api', __name__)

SERVER_URL = ''
API_TOKEN = ''


@redcap_api.route('/user/redcap/ZbeVRwRDvFQvVkWTybnC2AnG3ZR2w5', methods=['POST'])
def redcap_handler():
    # unsupported in PyCap
    def survey_queue_link(record_id: str):
        r = requests.post(SERVER_URL, data={
            'token': API_TOKEN,
            'content': 'surveyQueueLink',
            'format': 'json',
            'record': record_id,
        })
        if r.status_code == 200:
            return r.text
        else:
            return ''

    record_id = request.form.get('record', '')
    if not record_id:
        return jsonify({'msg': 'Missing record information'}), 400

    if ParticipantInfo.objects.filter(record_id__exact=record_id).exists():
        return jsonify({'msg': 'User exists'}), 304

    # create beiwe user and write credentials back to Redcap
    try:
        project = redcap.Project(SERVER_URL, API_TOKEN)
        records = project.export_records(records=[record_id])

        if not records:
            return jsonify({'msg': 'Records not found.'}), 400

        record = records[0]

        # Create user
        patient_id, password = Participant.create_with_password(study_id=1)
        patient = Participant.objects.get(patient_id__exact=patient_id)

        url = survey_queue_link(record_id)
        # TODO fill in such information
        ParticipantInfo(user=patient, country='United States', zipcode='78731', timezone='UTC',
                        record_id=record_id, queue_url=url).save()

        # Upload data back
        record['beiwe_username'] = patient_id
        record['beiwe_password'] = password
        response = project.import_records([record])
        if response['count'] != 1:
            return jsonify({'msg': 'Failed to update RedCap.'}), 304

        return jsonify({'msg': 'User created'}), 201
    except:
        return jsonify({'msg': 'Failed to create user'}), 400
