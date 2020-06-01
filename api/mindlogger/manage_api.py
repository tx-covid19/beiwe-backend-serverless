import json

from flask import Blueprint, jsonify
from flask_jwt_extended import (
    jwt_required, get_jwt_identity
)

from database.mindlogger_models import Activity, Applet
from database.notification_models import NotificationSubscription
from database.user_models import Participant
from libs import sns

manage_api = Blueprint('manage_api', __name__)


def subscribe_topic_if_not(applet: Applet, activity: Activity, participant: Participant):
    # only when user login on mobile device, do the subscription check
    if hasattr(participant, 'user_device') and participant.user_device.device_id and hasattr(activity,
                                                                                             'notification_topic'):
        topic = activity.notification_topic
        subscription_set = NotificationSubscription.objects.filter(subscriber=participant.user_device, topic=topic)
        if not subscription_set.exists():
            subscription_arn = sns.subscribe_to_topic(topic.sns_topic_arn, participant.user_device.endpoint_arn)
            if subscription_arn:
                NotificationSubscription(subscriber=participant.user_device, topic=topic,
                                         subscription_arn=subscription_arn).save()


@manage_api.route('/applets', methods=['GET'])
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

                # check subscription list every time when refreshing the page
                # in case that there may new applets added after user finishes registration.
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
@manage_api.route('/invites', methods=['GET'])
@jwt_required
def get_invites():
    return jsonify([]), 200
