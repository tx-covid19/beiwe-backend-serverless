import base64
import hashlib

from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    get_jwt_identity, jwt_refresh_token_required, jwt_required
)

from database.user_models import Participant
from database.userinfo_models import ParticipantInfo

participant_auth = Blueprint('participant_auth', __name__)


@participant_auth.route('/user/login', methods=['POST'])
def login():
    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request'}), 400

    patient_id = request.json.get('patient_id', None)
    password = request.json.get('password', None)

    if not patient_id or not password:
        return jsonify({'msg': 'Missing patient ID or password.'}), 400
    participant_set = Participant.objects.filter(patient_id=patient_id)
    if not participant_set.exists():
        return jsonify({'msg': 'User not found.'}), 401
    participant = participant_set.get()

    # encode password, as mobile clients do
    encoded_pwd = base64.b64encode(hashlib.sha256(password.encode()).digest(), b'-_').decode()
    if not participant.validate_password(encoded_pwd):
        return jsonify({'msg': 'Wrong password.'}), 401

    access_token = create_access_token(patient_id)
    refresh_token = create_refresh_token(patient_id)
    return jsonify({'access_token': access_token, 'refresh_token': refresh_token}), 200


@participant_auth.route('/user/refresh', methods=['POST'])
@jwt_refresh_token_required
def refresh():
    current_patient = get_jwt_identity()
    res = {
        'access_token': create_access_token(identity=current_patient)
    }
    return jsonify(res), 200


@participant_auth.route('/user/settings', methods=['PUT'])
@jwt_required
def settings():
    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request'}), 400
    current_patient = get_jwt_identity()
    info_set = ParticipantInfo.objects.filter(user__patient_id__exact=current_patient)
    if info_set.exists():
        info = info_set.get()
        fields = ['country', 'zipcode', 'timezone']
        for field in fields:
            if field in request.json:
                setattr(info, field, request.json[field])
        info.save()
        return jsonify({'msg': 'Info updated'}), 200
    else:
        user = Participant.objects.get(patient_id__exact=current_patient)
        info = ParticipantInfo(user=user, country=request.json.get('country', 'United States'),
                               zipcode=request.json.get('zipcode', '00001'),
                               timezone=request.json.get('timezone', 'UTC'))
        info.save()
        return jsonify({'msg': 'Created'}), 201
