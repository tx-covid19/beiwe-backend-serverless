from django.db import models

from database.user_models import Participant


class GPSMeasure(models.Model):
    user = models.ForeignKey(Participant, on_delete=models.PROTECT)
    last_updated = models.DateTimeField()
    distance = models.FloatField()
    standard_deviation = models.FloatField()
