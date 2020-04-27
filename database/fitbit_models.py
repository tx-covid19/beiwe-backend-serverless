from django.db import models

from database.user_models import Participant


class FitbitRecord(models.Model):
    user = models.OneToOneField(Participant, on_delete=models.CASCADE)
    refresh_token = models.TextField()
    access_token = models.TextField()
