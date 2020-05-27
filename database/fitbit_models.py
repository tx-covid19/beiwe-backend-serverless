from django.db import models

from database.user_models import Participant
from config.fitbit_constants import TIME_SERIES_TYPES, INTRA_TIME_SERIES_TYPES



class FitbitCredentials(models.Model):
    participant = models.OneToOneField(Participant, on_delete=models.CASCADE)
    refresh_token = models.TextField()
    access_token = models.TextField()

    def delete(self):
        # import here to avoid import-loop
        from libs.fitbit import delete_fitbit_records_trigger

        try:
            delete_fitbit_records_trigger(self)
        except:
            pass
        super(FitbitCredentials, self).delete()


class FitbitInfo(models.Model):
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    date = models.DateTimeField()

    devices = models.TextField()
    friends = models.TextField()
    friends_leaderboard = models.TextField()


class FitbitRecord(models.Model):
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    date = models.DateTimeField()

    class Meta:
        unique_together = ('participant', 'date',)

for data_stream, data_stream_type in TIME_SERIES_TYPES.items():
    data_stream = data_stream.replace('/', '_')
    if data_stream_type == '+int':
        FitbitRecord.add_to_class(data_stream, models.PositiveIntegerField(blank=True, null=True))
    elif data_stream_type == 'float':
        FitbitRecord.add_to_class(data_stream, models.FloatField(blank=True, null=True))
    elif data_stream_type == 'json':
        FitbitRecord.add_to_class(data_stream, models.TextField(blank=True, null=True))


class FitbitIntradayRecord(models.Model):
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    date = models.DateTimeField()

    class Meta:
        unique_together = ('participant', 'date',)

for data_stream, data_stream_type in INTRA_TIME_SERIES_TYPES.items():
    data_stream = data_stream.replace('/', '_')
    if data_stream_type == '+int':
        FitbitIntradayRecord.add_to_class(data_stream, models.PositiveIntegerField(blank=True, null=True))
    elif data_stream_type == 'float':
        FitbitIntradayRecord.add_to_class(data_stream, models.FloatField(blank=True, null=True))
    elif data_stream_type == 'json':
        FitbitIntradayRecord.add_to_class(data_stream, models.TextField(blank=True, null=True))
