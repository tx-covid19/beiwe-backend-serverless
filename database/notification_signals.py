from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from database.mindlogger_models import UserDevice, Activity
from database.notification_models import NotificationTopic, NotificationSubscription
from libs import sns

PLATFORM_ARN = ''


@receiver(post_save, sender=UserDevice)
def register_user_in_sns(sender, **kwargs):
    user_device: UserDevice = kwargs['instance']
    endpoint_arn = sns.create_user_endpoint(PLATFORM_ARN, user_device.device_id)
    if endpoint_arn:
        user_device.endpoint_arn = endpoint_arn
        user_device.save()


@receiver(pre_delete, sender=UserDevice)
def unregister_user_in_sns(sender, **kwargs):
    user_device: UserDevice = kwargs['instance']
    if user_device.endpoint_arn:
        for sub in NotificationSubscription.objects.filter(subscriber=user_device).all():
            sns.unsubscribe_topic(sub.subscription_arn)

        sns.delete_user_endpoint(user_device.endpoint_arn)


@receiver(post_save, sender=Activity)
def register_activity_as_topic(sender, **kwargs):
    activity: Activity = kwargs['instance']
    applet = activity.applet

    # deduplicate
    if NotificationTopic.objects.filter(applet=applet, activity=activity).exists():
        return

    topic_arn = sns.create_topic(applet.pk, activity.pk)
    if topic_arn:
        try:
            NotificationTopic(applet=applet, activity=activity, sns_topic_arn=topic_arn).save()
        except:
            # logging
            pass


@receiver(pre_delete, sender=Activity)
def unregister_activity_as_topic(sender, **kwargs):
    activity: Activity = kwargs['instance']
    applet = activity.applet
    try:
        topic = NotificationTopic.objects.get(applet=applet, activity=activity)
        topic_arn = topic.sns_topic_arn
        sns.delete_topic(topic_arn)
        topic.delete()
    except:
        pass