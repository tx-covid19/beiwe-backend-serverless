import datetime
import json
import random

from django.db import transaction
from flask import Blueprint, jsonify, request, abort
from flask_jwt_extended import jwt_required

from database.mindlogger_models import Applet, Activity, Screen, Event
from database.notification_models import NotificationTopic, NotificationEvent
from database.study_models import Study
from libs import eventbridge

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


@applet_api.route('/<applet_id>/schedule', methods=['GET'])
@jwt_required
def get_schedule(applet_id):
    try:
        events = Event.objects.filter(applet__pk=applet_id)
        return jsonify(assemble_outputs([json.loads(e.event) for e in list(events)])), 200
    except:
        return jsonify(assemble_outputs([])), 200


def submit_schedule(cron_expr, applet, activity, event):
    # assert all old schedules have been cleaned up
    # use timestamp to avoid duplicate names for multiple events towards the same topic
    ts = datetime.datetime.now().timestamp()
    event_rule_name = 'mindlogger-applet-{}-activity-{}-{}'.format(applet.pk, activity.pk, ts)

    try:
        topic = NotificationTopic.objects.get(applet=applet, activity=activity)
    except:
        return False

    if eventbridge.create_or_update_event(event_rule_name, cron_expr,
                                          'mindlogger-applet-{}-activity-{}'.format(applet.pk, activity.pk),
                                          topic.sns_topic_arn,
                                          json.dumps(
                                              dict(head=event['data']['title'],
                                                   content=event['data']['description'])
                                          )):
        NotificationEvent(topic=topic, eventbridge_name=event_rule_name, rules=cron_expr,
                          head=event['data']['title'], content=event['data']['description']).save()

    return True


def random_date(start, end, format_str='%H:%M'):
    start_date = datetime.datetime.strptime(start, format_str)
    end_date = datetime.datetime.strptime(end, format_str)

    time_between_dates = end_date - start_date
    days_between_dates = time_between_dates.seconds
    random_number_of_seconds = random.randrange(days_between_dates)
    return start_date + datetime.timedelta(seconds=random_number_of_seconds)


def set_push_notification(event, applet, activity):
    if 'data' not in event or 'schedule' not in event:
        return

    start_time = event['data']['notifications'][0]['start']
    end_time = event['data']['notifications'][0]['end']
    if event['data']['notifications'][0]['random']:
        scheduled_time = random_date(start_time, end_time).strftime('%H:%M')
    else:
        scheduled_time = start_time

    hour, minute = scheduled_time.split(':')
    hour = int(hour)
    minute = int(minute)

    if 'dayOfMonth' in event['schedule']:
        """
        Schedule once
        """
        if 'year' in event['schedule'] and 'month' in event['schedule'] and 'dayOfMonth' in event['schedule']:
            try:
                year = int(event['schedule']['year'][0])
                month = int(event['schedule']['month'][0]) + 1
                day = int(event['schedule']['dayOfMonth'][0])
            except:
                return

            submit_schedule('{} {} {} {} {} {}'.format(minute, hour, day, month, '?', year), applet, activity, event)

    else:
        start_date = None
        end_date = None
        if 'start' in event['schedule'] and event['schedule']['start']:
            start_date = datetime.datetime.fromtimestamp(float(event['schedule']['start']) / 1000)
        if 'end' in event['schedule'] and event['schedule']['end']:
            end_date = datetime.datetime.fromtimestamp(float(event['schedule']['end']) / 1000)

        if start_date and end_date:
            # TODO does not work for start_date.day > end_date.day, it leads to invalid cron exprs.
            day_range = str(start_date.day) + '-' + str(end_date.day)
            month_range = str(start_date.month) + '-' + str(end_date.month)
            year_range = str(start_date.year) + '-' + str(end_date.year)

            if 'dayOfWeek' in event['schedule']:
                day_of_week = int(event['schedule']['dayOfWeek'][0])
                submit_schedule(
                    '{} {} {} {} {} {}'.format(minute, hour, day_range, month_range, day_of_week, year_range), applet,
                    activity, event)
            else:
                submit_schedule(
                    '{} {} {} {} {} {}'.format(minute, hour, day_range, month_range, '?', year_range), applet, activity,
                    event)
        else:
            if 'dayOfWeek' in event['schedule']:
                day_of_week = int(event['schedule']['dayOfWeek'][0])
                submit_schedule(
                    '{} {} {} {} {} {}'.format(minute, hour, '*', '*', day_of_week, '*'), applet, activity, event)
            else:
                submit_schedule(
                    '{} {} {} {} {} {}'.format(minute, hour, '*', '*', '?', '*'), applet, activity, event)


@applet_api.route('/<applet_id>/schedule', methods=['PUT'])
@jwt_required
def set_schedule(applet_id):
    try:
        schedule = json.loads(request.form.get('schedule'))
        applet = Applet.objects.get(pk=applet_id)
    except:
        return {
            "applet": {
                "schedule": {}
            }
        }

    if 'events' in schedule:
        # insert and update events/notifications
        for event in schedule['events']:
            if 'data' not in event or 'URI' not in event['data']:
                continue
            URI = event['data']['URI']
            try:
                activity = Activity.objects.get(URI__exact=URI, applet__pk=applet_id)
                with transaction.atomic():
                    # remove the existing events and readd again
                    # must clean up all push notifications because there might be many multiple events to one topic
                    # which makes modifying existing records very tricky
                    Event.objects.filter(applet__pk=applet_id, activity=activity).delete()
                    NotificationEvent.objects.filter(topic=activity.notification_topic).delete()
            except:
                return abort(400)

            db_event = Event(applet=applet, activity=activity, event=json.dumps(event))
            db_event.save()
            event['id'] = db_event.pk
            db_event.event = json.dumps(event)
            db_event.save()

            if 'data' in event and 'useNotifications' in event['data'] and event['data']['useNotifications']:
                if 'notifications' in event['data'] and event['data']['notifications'][0]['start']:
                    set_push_notification(event, applet, activity)

    return {
        "applet": {
            "schedule": schedule
        }
    }
