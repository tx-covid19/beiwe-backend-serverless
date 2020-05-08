import json
import datetime
import random
from typing import List

from flask import Blueprint, jsonify
from pyfcm import FCMNotification

from database.applet_model import PushNotification, DeviceInfo, ProgressState
from database.user_models import Participant

push_notification_api = Blueprint('push_notification_api', __name__)
push_service = FCMNotification(
    api_key="AAAAzx5qnMU:APA91bHN69uvnLu71d9XJu9_t1qp0XefAL2IdNiVka-0CxMMq9eKiM5zxP_rAF2W0IW48evVLzefgCt-gSPJyDKjUmkIU95xBevowomvS1obdLXl9TexeqTp1mrGmyHf5-ObN3hpXCDO")


def send_notification(notification: PushNotification, user_ids: list):
    message_title = notification.head
    message_body = notification.content
    result = push_service.notify_multiple_devices(registration_ids=user_ids,
                                                  message_title=message_title,
                                                  message_body=message_body)
    notification.attempts += 1
    notification.progress = ProgressState.ACTIVE
    if result['failure']:
        notification.progress = ProgressState.ERROR
        notification.date_send = datetime.datetime.utcnow()

    if result['success']:
        notification.progress = ProgressState.SUCCESS

    notification.save()
    return result


def random_date(start, end, format_str='%H:%M'):
    start_date = datetime.datetime.strptime(start, format_str)
    end_date = datetime.datetime.strptime(end, format_str)

    time_between_dates = end_date - start_date
    days_between_dates = time_between_dates.seconds
    random_number_of_seconds = random.randrange(days_between_dates)
    return start_date + datetime.timedelta(seconds=random_number_of_seconds)


# TODO repeatable schedule
# def refresh_notification_users(current_time, notification: PushNotification, user):
#     if not notification.notification_type == 1:
#         current_user_time = datetime.datetime.strptime(current_time, '%Y/%m/%d %H:%M') \
#                             + datetime.timedelta(hours=int(user['timezone']))
#
#         notification_schedule = json.loads(notification.schedule)
#         notification_start_date = notification_schedule['start']
#         notification_end_date = notification_schedule['end']
#
#         date_notified_last_date = self.__list_filter(notification['notifiedUsers'], '_id', user['_id'])
#
#         if notification_start_date <= current_user_time.strftime('%Y/%m/%d') \
#                 <= notification_end_date:
#             if 'dateSend' in date_notified_last_date and date_notified_last_date['dateSend'] \
#                     < current_user_time.strftime('%Y/%m/%d'):
#                 notification['notifiedUsers'] = \
#                     self.__exclude_from_list(notification['notifiedUsers'], '_id', user['_id'])


def filter_users(current_time, notification: PushNotification, users: List[Participant]):
    current_users = []

    notification_schedule = json.loads(notification.schedule)
    notification_start_date = notification_schedule['start']
    notification_end_date = notification_schedule['end']
    notification_week_day = notification_schedule.get('dayOfWeek', None)

    notification_start_time = notification.start_time
    notification_end_time = notification.end_time

    notification_h = int(
        datetime.datetime.strptime(notification_start_time, "%H:%M").hour)
    notification_m = int(
        datetime.datetime.strptime(notification_start_time, "%H:%M").minute)

    notification_random_h = None
    notification_random_m = None
    if notification.last_random_time:
        notification_random_h = int(
            datetime.datetime.strptime(notification.last_random_time, "%H:%M").hour)
        notification_random_m = int(
            datetime.datetime.strptime(notification.last_random_time, "%H:%M").minute)

    for user in users:
        if not hasattr(user, 'device_info'):
            continue
        current_user_time = datetime.datetime.strptime(current_time, '%Y/%m/%d %H:%M') \
                            + datetime.timedelta(hours=int(user.device_info.timezone))

        # refresh_notification_users(notification, user)

        usr_h = int(current_user_time.strftime("%H"))
        usr_m = int(current_user_time.strftime("%M"))

        if current_user_time.strftime('%H:%M') >= notification_start_time \
                and notification_start_date <= current_user_time.strftime('%Y/%m/%d') \
                <= notification_end_date:
            current_users.append(user)

            # if notification.notification_type in [1, 2]:
            #     if notification_end_time and notification.last_random_time \
            #             and current_user_time.strftime('%H:%M') \
            #             >= notification.last_random_time.strftime('%H:%M') and usr_h == notification_random_h \
            #             and usr_m >= notification_random_m:
            #         # in random time case for single\daily notification
            #         current_users.append(user)
            #     if not notification_end_time and usr_h == notification_h \
            #             and usr_m >= notification_m:
            #         # in single\daily notification case
            #         current_users.append(user)

            # if notification.notification_type == 3:
            #     if notification_week_day and notification_week_day == int(current_user_time.weekday()) + 1:
            #         if notification_end_time and notification['lastRandomTime'] \
            #                 and current_user_time.strftime('%H:%M') \
            #                 >= notification['lastRandomTime'] and usr_h == notification_random_h \
            #                 and usr_m >= notification_random_m:
            #             # in random time case for weekly notification case
            #             current_users.append(user)
            #
            #         if not notification_end_time and usr_h == notification_h and usr_m >= notification_m:
            #             # in weekly notification case
            #             current_users.append(user)
    return current_users


@push_notification_api.route('/send_notification', methods=['GET'])
def notify():
    for notification in PushNotification.objects.all():
        if notification.progress == ProgressState.ACTIVE:
            current_time = datetime.datetime.utcnow().strftime('%Y/%m/%d %H:%M')
            users = notification.applet.study.participants.all()
            users_to_notify = filter_users(current_time, notification, users)
            send_notification(notification, [user.device_info.device_id for user in users_to_notify])

    return 'Done', 200
