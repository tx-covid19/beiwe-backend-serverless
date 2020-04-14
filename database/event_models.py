from django.contrib.postgres.fields import JSONField
from django.db import models

from libs import timezone
from .user_models import Participant


class Event(models.Model):
    """
    Model to track user interaction with the frontend.
    """
    user = models.ForeignKey(Participant, on_delete=models.PROTECT)
    date = models.DateTimeField(default=timezone.now)

    event = models.CharField(max_length=50)
    metadata = JSONField()
