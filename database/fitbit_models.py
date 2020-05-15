from django.db import models

from database.user_models import Participant
from config.fitbit_constants import TIME_SERIES_TYPES, INTRA_TIME_SERIES_TYPES


class FitbitCredentials(models.Model):
    user = models.OneToOneField(Participant, on_delete=models.CASCADE)
    refresh_token = models.TextField()
    access_token = models.TextField()


class FitbitRecord(models.Model):
    user = models.ForeignKey(Participant, on_delete=models.CASCADE)
    last_updated = models.DateTimeField()

    devices = models.TextField()
    friends = models.TextField()
    friends_leaderboard = models.TextField()

for k, type_str in TIME_SERIES_TYPES.items():
    k = k.replace('/', '_')
    if type_str == '+int':
        FitbitRecord.add_to_class(k, models.PositiveIntegerField(blank=True, null=True))
    elif type_str == 'float':
        FitbitRecord.add_to_class(k, models.FloatField(blank=True, null=True))
    elif type_str == 'json':
        FitbitRecord.add_to_class(k, models.TextField(blank=True, null=True))


class FitbitIntradayRecord(models.Model):
    user = models.ForeignKey(Participant, on_delete=models.CASCADE)
    last_updated = models.DateTimeField()

for k, type_str in INTRA_TIME_SERIES_TYPES.items():
    k = k.replace('/', '_')
    if type_str == '+int':
        FitbitIntradayRecord.add_to_class(k, models.PositiveIntegerField(blank=True, null=True))
    elif type_str == 'float':
        FitbitIntradayRecord.add_to_class(k, models.FloatField(blank=True, null=True))
    elif type_str == 'json':
        FitbitIntradayRecord.add_to_class(k, models.TextField(blank=True, null=True))
