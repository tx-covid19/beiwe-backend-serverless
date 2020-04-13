from django.db import models

from .user_models import Participant


class ParticipantInfo(models.Model):
    user = models.OneToOneField(Participant, on_delete=models.PROTECT)

    country = models.CharField(max_length=100)
    zipcode = models.CharField(max_length=20)
    timezone = models.CharField(max_length=100)
