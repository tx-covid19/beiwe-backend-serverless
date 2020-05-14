from django.db import models

from database.mindlogger_models import Activity, Applet, UserDevice


class NotificationTopic(models.Model):
    last_updated = models.DateTimeField(auto_now=True)
    applet = models.ForeignKey(Applet, on_delete=models.CASCADE)
    activity = models.OneToOneField(Activity, on_delete=models.CASCADE, related_name='notification_topic')
    sns_topic_arn = models.TextField()


class NotificationEvent(models.Model):
    last_updated = models.DateTimeField(auto_now=True)
    topic = models.ForeignKey(NotificationTopic)
    eventbridge_name = models.TextField()
    rules = models.TextField()
    head = models.TextField()
    content = models.TextField()


class NotificationSubscription(models.Model):
    last_updated = models.DateTimeField(auto_now=True)
    subscriber = models.ForeignKey(UserDevice, on_delete=models.CASCADE)
    topic = models.ForeignKey(NotificationTopic, on_delete=models.CASCADE)
    subscription_arn = models.TextField()

    class Meta:
        unique_together = ('subscriber', 'topic',)
