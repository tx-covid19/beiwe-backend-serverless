import json
import time

from django.db import models
import datetime
from database.models import AbstractModel, JSONTextField, Participant


class AbstractMindloggerModel(AbstractModel):
    class Meta:
        abstract = True


class DeviceInfo(AbstractModel):
    user = models.OneToOneField(Participant, on_delete=models.CASCADE, related_name='device_info')
    timezone = models.IntegerField()
    device_id = models.TextField()


class Applet(AbstractMindloggerModel):
    study = models.ForeignKey('Study', on_delete=models.PROTECT, related_name='applets')
    content = JSONTextField()
    protocol = JSONTextField()


class Activity(AbstractMindloggerModel):
    applet = models.ForeignKey(Applet, on_delete=models.PROTECT, related_name='activities')
    URI = models.TextField()
    content = JSONTextField()


class Screen(AbstractMindloggerModel):
    activity = models.ForeignKey(Activity, on_delete=models.PROTECT, related_name='screens')
    URI = models.TextField()
    content = JSONTextField()


class Response(AbstractMindloggerModel):
    user = models.ForeignKey(Participant, on_delete=models.PROTECT)
    screen = models.ForeignKey(Screen, on_delete=models.PROTECT, related_name='responses')
    value = JSONTextField()


class Event(AbstractMindloggerModel):
    applet = models.ForeignKey(Applet)
    event = JSONTextField()


class ProgressState(object):
    ACTIVE = 'active'
    SUCCESS = 'success'
    ERROR = 'error'
    EMPTY = 'empty'


class PushNotification(AbstractMindloggerModel):
    PROGRESS_CHOICES = [
        (ProgressState.ACTIVE, ProgressState.ACTIVE),
        (ProgressState.SUCCESS, ProgressState.SUCCESS),
        (ProgressState.ERROR, ProgressState.ERROR),
        (ProgressState.EMPTY, ProgressState.EMPTY),
    ]

    NOTIFICATION_TYPE = [
        (1, 'no repeat'),
        (2, 'weekly'),
        (3, 'daily')
    ]

    applet = models.ForeignKey(Applet)
    referenced_event = models.ForeignKey(Event)
    notification_type = models.IntegerField(choices=NOTIFICATION_TYPE)
    head = models.TextField(blank=True)
    content = models.TextField(blank=True)
    schedule = JSONTextField()
    start_time = models.TextField(blank=True, null=True)
    end_time = models.TextField(blank=True, null=True)
    last_random_time = models.DateTimeField(blank=True, null=True)
    date_send = models.DateTimeField(blank=True, null=True)
    progress = models.TextField(choices=PROGRESS_CHOICES)
    attempts = models.PositiveIntegerField()

    @classmethod
    def update_notification(cls, applet, event, event_data, user_info, original=None):
        current_date = datetime.datetime.utcnow()
        current_user_date = current_date + datetime.timedelta(hours=int(user_info['timezone']))
        notification_type = 1
        start_time = event_data['data']['notifications'][0]['start']
        end_time = event_data['data']['notifications'][0]['end']

        schedule = {
            "start": (current_date - datetime.timedelta(days=1)).strftime('%Y/%m/%d'),
            "end": (current_date + datetime.timedelta(days=365 * 40)).strftime('%Y/%m/%d')
        }

        if 'schedule' in event_data:
            if 'dayOfMonth' in event_data['schedule']:
                """
                Does not repeat configuration in case of single event with exact year, month, day
                """
                if event_data['data'].get('notifications', None) and \
                        event_data['data']['notifications'][0]['random']:
                    end_time = event_data['data']['notifications'][0]['end']
                if 'year' in event_data['schedule'] and 'month' in event_data['schedule'] \
                        and 'dayOfMonth' in event_data['schedule']:
                    current_date_schedule = str(str(event_data['schedule']['year'][0]) + '/' +
                                                ('0' + str(event_data['schedule']['month'][0] + 1))[-2:] + '/' +
                                                ('0' + str(event_data['schedule']['dayOfMonth'][0]))[-2:])
                    schedule['start'] = current_date_schedule
                    schedule['end'] = current_date_schedule

            elif 'dayOfWeek' in event_data['schedule']:
                """
                Weekly configuration in case of weekly event
                """
                notification_type = 3
                if 'start' in event_data['schedule'] and event_data['schedule']['start']:
                    schedule['start'] = datetime.datetime.fromtimestamp(
                        float(event_data['schedule']['start']) / 1000).strftime('%Y/%m/%d')
                if 'end' in event_data['schedule'] and event_data['schedule']['end']:
                    schedule['end'] = datetime.datetime.fromtimestamp(
                        float(event_data['schedule']['end']) / 1000).strftime('%Y/%m/%d')
                schedule['dayOfWeek'] = event_data['schedule']['dayOfWeek'][0]
            else:
                """
                Daily configuration in case of daily event
                """
                notification_type = 2
                if 'start' in event_data['schedule'] and event_data['schedule']['start']:
                    schedule['start'] = datetime.datetime.fromtimestamp(
                        float(event_data['schedule']['start']) / 1000).strftime('%Y/%m/%d')
                if 'end' in event_data['schedule'] and event_data['schedule']['end']:
                    schedule['end'] = datetime.datetime.fromtimestamp(
                        float(event_data['schedule']['end']) / 1000).strftime('%Y/%m/%d')

            push_notification = {
                'referenced_event': event,
                'applet': applet,
                'notification_type': notification_type,
                'head': event_data['data']['title'],
                'content': event_data['data']['description'],
                'schedule': json.dumps(schedule),
                'start_time': start_time,
                'end_time': end_time,
                'last_random_time': None,
                'date_send': None,
                'progress': ProgressState.ACTIVE,
                'attempts': 0
            }

            # if original:
            #     push_notification.update({
            #         '_id': original.get('_id'),
            #         'progress': original.get('progress'),
            #         'attempts': original.get('attempts'),
            #         'dateSend': original.get('dateSend'),
            #         'notifiedUsers': self.update_notified_users(push_notification),
            #         'lastRandomTime': original.get('lastRandomTime')
            #     })
            #
            #     if start_time > current_user_date.strftime('%H:%M') \
            #             and schedule['start'] >= current_user_date.strftime('%Y/%m/%d'):
            #         push_notification.update({
            #             'progress': ProgressState.ACTIVE,
            #             'lastRandomTime': None
            #         })
            cls(**push_notification).save()
