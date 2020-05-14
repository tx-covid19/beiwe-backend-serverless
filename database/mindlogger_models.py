from django.db import models

from database.models import AbstractModel, JSONTextField, Participant


class AbstractMindloggerModel(AbstractModel):
    class Meta:
        abstract = True


class UserDevice(AbstractModel):
    user = models.OneToOneField(Participant, on_delete=models.CASCADE, related_name='user_device')
    timezone = models.IntegerField()
    device_id = models.TextField()
    endpoint_arn = models.TextField(blank=True, null=True)


class Applet(AbstractMindloggerModel):
    study = models.ForeignKey('Study', on_delete=models.CASCADE, related_name='applets')
    content = JSONTextField()
    protocol = JSONTextField()


class Activity(AbstractMindloggerModel):
    applet = models.ForeignKey(Applet, on_delete=models.CASCADE, related_name='activities')
    URI = models.TextField(unique=True)
    content = JSONTextField()


class Screen(AbstractMindloggerModel):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='screens')
    URI = models.TextField(unique=True)
    content = JSONTextField()


class Response(AbstractMindloggerModel):
    user = models.ForeignKey(Participant, on_delete=models.CASCADE)
    screen = models.ForeignKey(Screen, on_delete=models.SET_NULL, related_name='responses', null=True)
    value = JSONTextField()


class Event(AbstractMindloggerModel):
    applet = models.ForeignKey(Applet, on_delete=models.CASCADE)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE)
    event = JSONTextField()
