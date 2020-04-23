from django.db import models

from .user_models import Participant


class RedcapRecord(models.Model):
    user = models.OneToOneField(Participant, on_delete=models.CASCADE)
    record_id = models.CharField(max_length=50, unique=True)
