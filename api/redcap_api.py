import redcap
from flask import Blueprint, request, jsonify

from config.settings import IS_SERVERLESS, REDCAP_CONSENT_FORM_NAME, REDCAP_BEIWE_USERNAME_FIELD, \
    REDCAP_BEIWE_PASSWORD_FIELD
from database.redcap_models import RedcapRecord
from database.study_models import Study
from database.system_integrations import RedcapIntegration
from database.user_models import Participant, StudyRelation
from database.user_models import Researcher
from libs.s3 import s3_upload, create_client_key_pair

redcap_api = Blueprint('redcap_api', __name__)


def create_beiwe_patient(study_id):
    patient_id, password = Participant.create_with_password(study_id=study_id)
    study_object_id = Study.objects.filter(pk=study_id).values_list('object_id', flat=True).get()
    s3_upload(patient_id, b"", study_object_id)
    if IS_SERVERLESS is False:
        create_client_key_pair(patient_id, study_object_id)
    return patient_id, password


@redcap_api.route('/user/redcap', methods=['POST'])
def redcap_handler():
    instrument = request.form.get('instrument', '')
    instrument_completed = request.form.get(REDCAP_CONSENT_FORM_NAME + '_complete', '')
    event_user = request.form.get('username', '')
    record_id = request.form.get('record', '')

    # filter unrelated requests quickly
    if instrument != REDCAP_CONSENT_FORM_NAME or instrument_completed != '2' or event_user != '[survey respondent]':
        return jsonify({'msg': 'Request ignored.'}), 200

    if not record_id:
        return jsonify({'msg': 'Missing record information'}), 200

    study_id = request.args.get('study_id', '')
    access_key = request.args.get('access_key', '')
    access_secret = request.args.get('access_secret', '')

    if not study_id:
        return jsonify({'msg': 'No study ID supplied.'}), 400

    # do authentication
    try:
        researcher = Researcher.objects.get(access_key_id=access_key)
    except Researcher.DoesNotExist:
        return jsonify({'msg': 'No access.'}), 403

    if not researcher.is_study_admin() or not StudyRelation.objects.filter(study_id=study_id,
                                                                           researcher=researcher).exists():
        return jsonify({'msg': 'Not authorized for this study.'}), 403

    if not researcher.validate_access_credentials(access_secret):
        return jsonify({'msg': 'Wrong secrets.'}), 403

    # check duplicates in Redcap records, (study, record_id) must be unique.
    if RedcapRecord.objects.filter(study__pk=study_id, record_id__exact=record_id).exists():
        return jsonify({'msg': 'Record exists.'}), 304

    # create beiwe user and write credentials back to Redcap
    try:
        study = Study.objects.get(pk=study_id)
        credentials = RedcapIntegration.objects.get(study__exact=study)
        project = redcap.Project(credentials.server_url, credentials.api_token)
        records = project.export_records(records=[record_id])

        if not records:
            return jsonify({'msg': 'Records not found.'}), 404

        record = records[0]

        # Create user
        patient_id, password = create_beiwe_patient(study_id)
        patient = Participant.objects.get(patient_id__exact=patient_id)
        RedcapRecord(user=patient, record_id=record_id, study=study).save()

        # Upload data back
        record[REDCAP_BEIWE_USERNAME_FIELD] = patient_id
        record[REDCAP_BEIWE_PASSWORD_FIELD] = password
        response = project.import_records([record])
        if response['count'] != 1:
            return jsonify({'msg': 'Failed to update RedCap.'}), 304

        return jsonify({'msg': 'User created'}), 201
    except Exception:
        return jsonify({'msg': 'Server error.'}), 500
