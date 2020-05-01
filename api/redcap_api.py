import redcap
from flask import Blueprint, request, jsonify

from config.settings import REDCAP_SERVER_URL, REDCAP_API_TOKEN
from database.redcap_models import RedcapRecord
from database.user_models import Participant, StudyRelation
from database.user_models import Researcher
from libs.s3 import s3_upload

redcap_api = Blueprint('redcap_api', __name__)

EXPECTED_INSTRUMENT_NAME = 'online_consent_form'


@redcap_api.route('/user/redcap', methods=['POST'])
def redcap_handler():
    instrument = request.form.get('instrument', '')
    instrument_completed = request.form.get(EXPECTED_INSTRUMENT_NAME + '_complete', '')
    event_user = request.form.get('username', '')

    print(request.form)

    if instrument != EXPECTED_INSTRUMENT_NAME or instrument_completed != '2' or event_user != '[survey respondent]':
        print('ignoring request 200')
        return jsonify({'msg': 'Request ignored.'}), 200

    study_id = request.args.get('study_id', '')
    access_key = request.args.get('access_key', '')
    access_secret = request.args.get('access_secret', '')

    if not study_id:
        print('no study id 400')
        return jsonify({'msg': 'No study ID supplied.'}), 400

    try:
        researcher = Researcher.objects.get(access_key_id=access_key)
    except Researcher.DoesNotExist:
        print("researcher not found 403")
        return jsonify({'msg': 'No access.'}), 403

    if not researcher.site_admin and not StudyRelation.objects.filter(study_id=study_id, researcher=researcher).exists():
        print("not authorized 403")
        return jsonify({'msg': 'Not authorized for this study.'}), 403

    if not researcher.validate_access_credentials(access_secret):
        print("access secret 403")
        return jsonify({'msg': 'Wrong secrets.'}), 403

    record_id = request.form.get('record', '')

    if not record_id:
        print('no record id 400')
        return jsonify({'msg': 'Missing record information'}), 400

    if RedcapRecord.objects.filter(record_id__exact=record_id).exists():
        print('record id already exists 400')
        return jsonify({'msg': 'User exists'}), 304

    # create beiwe user and write credentials back to Redcap
    try:
        project = redcap.Project(REDCAP_SERVER_URL, REDCAP_API_TOKEN)
        records = project.export_records(records=[record_id])

        if not records:
            print('records not found 400')
            return jsonify({'msg': 'Records not found.'}), 400

        record = records[0]

        # Create user
        patient_id, password = Participant.create_with_password(study_id=study_id)
        patient = Participant.objects.get(patient_id__exact=patient_id)
        s3_upload(patient_id, b"", patient.study.object_id)

        RedcapRecord(user=patient, record_id=record_id).save()

        # Upload data back
        record['beiwe_username'] = patient_id
        record['beiwe_password'] = password
        response = project.import_records([record])
        if response['count'] != 1:
            return jsonify({'msg': 'Failed to update RedCap.'}), 304

        return jsonify({'msg': 'User created'}), 201
    except Exception as e:
        print('failed to create user 400')
        print(e)
        return jsonify({'msg': 'Failed to create user'}), 400
