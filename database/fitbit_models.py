from django.db import models

from database.user_models import Participant
from config.fitbit_constants import TIME_SERIES_TYPES, INTRA_TIME_SERIES_TYPES


class FitbitCredentials(models.Model):
    """
    FitbitCredentials model is used to store Fitbit oAuth2 credentials, linked to a participant.
    """

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
    """
    FitbitInfo model is used to store data that has no history via Fitbit
    API e.g. the linked devices of a user. For these data, it is not possible
    to query the API for their past values. The values in this model represent
    the state of the information at the given time `date`, in which the data
    was queried. Considering this, it is important to notice that past information
    may get lost if the rows are deleted.
    """
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    date = models.DateTimeField()

    devices = models.TextField()
    friends = models.TextField()
    friends_leaderboard = models.TextField()


class FitbitRecord(models.Model):
    """
    FitbitInfo model is used to store the daily aggregated data from Fitbit.
    This information is present in the glanularity of a day.
    """
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    date = models.DateTimeField()

    class Meta:
        unique_together = ('participant', 'date',)


for data_stream, data_stream_type in TIME_SERIES_TYPES.items():
    data_stream = data_stream.replace('/', '_')
    if data_stream_type == '+int':
        FitbitRecord.add_to_class(
            data_stream, models.PositiveIntegerField(blank=True, null=True))
    elif data_stream_type == 'float':
        FitbitRecord.add_to_class(
            data_stream, models.FloatField(blank=True, null=True))
    elif data_stream_type == 'json':
        FitbitRecord.add_to_class(
            data_stream, models.TextField(blank=True, null=True))


class FitbitIntradayRecord(models.Model):
    """
    FitbitIntradayRecord model is used to store the intra-daily aggregated
    data from Fitbit. This information is present in the glanularity of a
    minute or a second (for heart rate).
    """
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    date = models.DateTimeField()

    class Meta:
        unique_together = ('participant', 'date',)


for data_stream, data_stream_type in INTRA_TIME_SERIES_TYPES.items():
    data_stream = data_stream.replace('/', '_')
    if data_stream_type == '+int':
        FitbitIntradayRecord.add_to_class(
            data_stream, models.PositiveIntegerField(blank=True, null=True))
    elif data_stream_type == 'float':
        FitbitIntradayRecord.add_to_class(
            data_stream, models.FloatField(blank=True, null=True))
    elif data_stream_type == 'json':
        FitbitIntradayRecord.add_to_class(
            data_stream, models.TextField(blank=True, null=True))
