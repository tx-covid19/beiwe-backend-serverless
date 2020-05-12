from django.db import models

from database.user_models import Participant


class GPSMeasure(models.Model):
    user = models.ForeignKey(Participant, on_delete=models.PROTECT)
    last_updated = models.DateTimeField()
    duration = models.PositiveIntegerField()
    distance = models.FloatField()
    standard_deviation = models.FloatField()
    n = models.PositiveIntegerField()
