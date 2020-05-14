import base64
import datetime
import hashlib
import json

from flask import Blueprint, request, jsonify, abort
from flask_jwt_extended import (
    create_access_token, jwt_required, get_jwt_identity
)

from database.mindlogger_models import UserDevice, Activity, Applet
from database.notification_models import NotificationSubscription
from database.user_models import Participant
from libs import sns

user_api = Blueprint('user_api', __name__)


@user_api.route('/authentication', methods=['GET'])
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

    device_id = request.headers.get('deviceId', '')
    timezone = int(request.headers.get('timezone', 0))

    if device_id and not UserDevice.objects.filter(user=participant).exists():
        UserDevice(user=participant, timezone=timezone, device_id=device_id).save()

    expires = datetime.timedelta(days=365)
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


@user_api.route('/authentication', methods=['DELETE'])
@jwt_required
def logout():
    patient_id = get_jwt_identity()
    try:
        user_device = UserDevice.objects.get(user__patient_id__exact=patient_id)
        user_device.delete()
        return jsonify({'message': 'Log out successfully.'}), 200
    except:
        return abort(500)


def subscribe_topic_if_not(applet: Applet, activity: Activity, participant: Participant):
    if hasattr(participant, 'user_device') and participant.user_device.device_id:
        topic = activity.notification_topic
        subscription_set = NotificationSubscription.objects.filter(subscriber=participant.user_device, topic=topic)
        if not subscription_set.exists():
            subscription_arn = sns.subscribe_to_topic(topic.sns_topic_arn, participant.user_device.endpoint_arn)
            if subscription_arn:
                NotificationSubscription(subscriber=participant.user_device, topic=topic,
                                         subscription_arn=subscription_arn).save()


@user_api.route('/applets', methods=['GET'])
@jwt_required
def get_own_applets():
    patient_id = get_jwt_identity()
    res_list = []
    try:
        participant = Participant.objects.get(patient_id__exact=patient_id)
        applets = participant.study.applets.all()
        for applet in applets:
            item = {'groups': ["1"], 'activities': {}, 'items': {}, 'protocol': json.loads(applet.protocol),
                    'applet': json.loads(applet.content)}
            for activity in applet.activities.all():
                content = activity.content
                data = json.loads(content)
                item['activities'][activity.URI] = data

                subscribe_topic_if_not(applet, activity, participant)

                for screen in activity.screens.all():
                    name = screen.URI
                    content = screen.content
                    item['items'][name] = json.loads(content)

            res_list.append(item)
        return jsonify(res_list), 200
    except:
        return jsonify(res_list), 200


# always return empty array
@user_api.route('/invites', methods=['GET'])
def get_invites():
    return jsonify([]), 200
