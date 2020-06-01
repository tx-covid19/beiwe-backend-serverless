import base64
import datetime
import hashlib

from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, jwt_required, get_jwt_identity, get_raw_jwt
)

from database.mindlogger_models import UserDevice
from database.token_models import TokenBlacklist
from database.user_models import Participant

auth_api = Blueprint('auth_api', __name__)


@auth_api.route('/authentication', methods=['GET'])
def authentication():
    if 'Authorization' in request.headers:
        auth = request.headers.get('Authorization')
    elif 'Girder-Authorization' in request.headers:
        auth = request.headers.get('Girder-Authorization')
    else:
        return jsonify({'message': 'Missing authorization header', 'type': 'access'}), 400

    if auth[0:6] != 'Basic ':
        return jsonify({'message': 'Please use HTTP Basic Authentication', 'type': 'access'}), 401

    try:
        credentials = base64.b64decode(auth[6:]).decode('utf8')
        if ':' not in credentials:
            raise ValueError
    except:
        return jsonify({'message': 'Invalid HTTP Authorization header', 'type': 'access'}), 401

    user_id, password = credentials.split(':', 1)

    participant_set = Participant.objects.filter(patient_id=user_id)
    encoded_pwd = base64.b64encode(hashlib.sha256(password.encode()).digest(), b'-_').decode()
    if not participant_set.exists():
        return jsonify({'message': 'Incorrect user or password.', 'type': 'access'}), 401
    participant = participant_set.get()
    if not participant.validate_password(encoded_pwd):
        return jsonify({'message': 'Incorrect user or password.', 'type': 'access'}), 401

    # UserDevice is only for mindlogger
    device_id = request.headers.get('deviceId', '')
    timezone = int(request.headers.get('timezone', 0))
    if device_id:
        if UserDevice.objects.filter(user=participant).exists():
            if UserDevice.objects.get(user=participant).device_id != device_id:
                return jsonify({'message': 'You have logged in another device.', 'type': 'access'}), 401
        else:
            UserDevice(user=participant, timezone=timezone, device_id=device_id).save()

    expires = datetime.timedelta(days=30)
    token = create_access_token(user_id, expires_delta=expires)
    expire_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {"authToken": {"expires": expire_time,
                          "scope": ["core.user_auth"],
                          "token": token
                          },
            "message": "Login succeeded.",
            "user": {"_accessLevel": 2, "_id": user_id,
                     "_modelType": "user", "admin": "False",
                     "created": "2020-05-04T18:59:08.736000+00:00",
                     "creatorId": user_id,
                     "displayName": "Participant",
                     "email": "Disabled",
                     "emailVerified": True,
                     "firstName": "participant",
                     "login": "participant",
                     "otp": False,
                     "public": False,
                     "size": 0,
                     "status": "enabled"
                     }
            }


@auth_api.route('/authentication', methods=['DELETE'])
@jwt_required
def logout():
    patient_id = get_jwt_identity()
    TokenBlacklist.blacklist_token(get_raw_jwt())
    try:
        user_device = UserDevice.objects.get(user__patient_id__exact=patient_id)
        user_device.delete()
    except:
        pass
    return jsonify({'message': 'Log out successfully.'}), 200
