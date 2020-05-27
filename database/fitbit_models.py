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

for data_type, type_str in TIME_SERIES_TYPES.items():
    data_type = data_type.replace('/', '_')
    if type_str == '+int':
        FitbitRecord.add_to_class(data_type, models.PositiveIntegerField(blank=True, null=True))
    elif type_str == 'float':
        FitbitRecord.add_to_class(data_type, models.FloatField(blank=True, null=True))
    elif type_str == 'json':
        FitbitRecord.add_to_class(data_type, models.TextField(blank=True, null=True))


class FitbitIntradayRecord(models.Model):
    user = models.ForeignKey(Participant, on_delete=models.CASCADE)
    last_updated = models.DateTimeField()

for data_type, data_type_details in INTRA_TIME_SERIES_TYPES.items():
    data_type = data_type.replace('/', '_')
    if data_type_details['type'] == '+int':
        FitbitIntradayRecord.add_to_class(data_type, models.PositiveIntegerField(blank=True, null=True))
    elif data_type_details['type'] == 'float':
        FitbitIntradayRecord.add_to_class(data_type, models.FloatField(blank=True, null=True))
    elif data_type_details['type'] == 'json':
        FitbitIntradayRecord.add_to_class(data_type, models.TextField(blank=True, null=True))
