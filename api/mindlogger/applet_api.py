import json

from flask import Blueprint, jsonify, request, abort
from flask_jwt_extended import (
    jwt_required
)

from database.applet_model import Applet, Activity, Screen, Event, PushNotification
from database.study_models import Study

applet_api = Blueprint('applet_api', __name__)


def replace_id(db_obj, prefix: str):
    content_json = json.loads(db_obj.content)
    content_json['_id'] = prefix + '/' + str(db_obj.pk)
    db_obj.content = json.dumps(content_json)
    db_obj.save()


@applet_api.route('/<study_id>', methods=['POST'])
def create_applet(study_id):
    if not request.is_json:
        return abort(400)

    data = request.json

    # inspect the data
    # TODO add transaction and rollback
    required_keys = ['activities', 'items', 'protocol', 'applet']
    if any([key not in data for key in required_keys]):
        return abort(400)

    try:
        study = Study.objects.get(pk=study_id)
    except:
        return abort(400)

    # create applets
    protocol_json = data['protocol']
    applet_json = data['applet']
    db_applet = Applet(study=study, content=json.dumps(applet_json), protocol=json.dumps(protocol_json))
    db_applet.save()
    replace_id(db_applet, 'applet')

    # create activities
    activity_json: dict = data['activities']
    for URI, value in activity_json.items():
        db_activity = Activity(applet=db_applet, URI=URI, content=json.dumps(value))
        db_activity.save()
        replace_id(db_activity, 'activity')

    # create screens
    item_json: dict = data['items']
    for URI, value in item_json.items():
        # TODO connect item to activity
        db_screen = Screen(activity=db_activity, URI=URI, content=json.dumps(value))
        db_screen.save()
        replace_id(db_screen, 'screen')

    return jsonify({'message': 'Done.'}), 200


def assemble_outputs(events):
    return {
        "type": 2,
        "size": 1,
        "fill": True,
        "minimumSize": 0,
        "repeatCovers": True,
        "listTimes": False,
        "eventsOutside": True,
        "updateRows": True,
        "updateColumns": False,
        "around": 1585724400000,
        'events': events
    }


@applet_api.route('/<applet_id>/schedule', methods=['GET', 'PUT'])
@jwt_required
def handle_schedule(applet_id):
    if request.method == 'GET':
        try:
            events = Event.objects.filter(applet__pk=applet_id)
            return jsonify(assemble_outputs([json.loads(e.event) for e in list(events)])), 200
        except:
            return jsonify({}), 200

    elif request.method == 'PUT':
        schedule = json.loads(request.form.get('schedule'))
        applet = Applet.objects.get(pk=applet_id)
        Event.objects.filter(applet__pk=applet_id).delete()

        if 'events' in schedule:
            # insert and update events/notifications
            for event in schedule['events']:
                db_event = Event(applet=applet, event=json.dumps(event))
                db_event.save()
                if 'data' in event and 'useNotifications' in event['data'] and event['data']['useNotifications']:
                    if 'notifications' in event['data'] and event['data']['notifications'][0]['start']:
                        PushNotification.update_notification(applet, db_event, event, {
                            'timezone': 0
                        })
                        # in case of daily/weekly event
                        # exist_notification = None
                        #
                        # if 'id' in event:
                        #     exist_notification = PushNotification.objects.filter(referenced_event__pk=event['id'])
                        #
                        # if exist_notification:
                        #     PushNotificationModel().replaceNotification(
                        #         applet['_id'],
                        #         savedEvent,
                        #         thisUser,
                        #         exist_notification)
                        # else:
                        #     PushNotificationModel().replaceNotification(
                        #         applet['_id'],
                        #         savedEvent,
                        #         thisUser)
                event['id'] = db_event.pk
                db_event.event = json.dumps(event)
                db_event.save()
        return {
            "applet": {
                "schedule": schedule
            }
        }
