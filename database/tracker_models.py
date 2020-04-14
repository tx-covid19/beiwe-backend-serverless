from datetime import datetime

from django.db import models

from libs import timezone
from .user_models import Participant
from .userinfo_models import ParticipantInfo


class TrackRecord(models.Model):
    user = models.ForeignKey(Participant, on_delete=models.PROTECT)
    last_update = models.DateTimeField(default=timezone.now)

    track_date = models.DateTimeField(unique=True)
    cost_category = models.CharField(max_length=100)
    cost = models.FloatField()

    people_interacted = models.PositiveIntegerField()
    screen_time = models.PositiveIntegerField()
    mood = models.CharField(max_length=20)

    weight = models.FloatField()
    temperature = models.FloatField()

    @classmethod
    def _get_timezone(cls, patient_id):
        info_set = ParticipantInfo.objects.filter(user__patient_id__exact=patient_id)
        if info_set.exists():
            info = info_set.get()
            tz = info.timezone
        else:
            tz = 'UTC'
        return tz

    @classmethod
    def _parse_to_utc(cls, date_string, tz):
        if not date_string:
            return None
        return timezone.to_utc(datetime.strptime(date_string, '%Y-%m-%d %H:%M:%S'), tz)

    def save(self, *args, **kwargs):
        patient_id = self.user.patient_id
        tz = self._get_timezone(patient_id)
        self.track_date = self._parse_to_utc(self.track_date, tz)
        super(TrackRecord, self).save()

    @classmethod
    def get_with_timezone(cls, patient_id):
        tz = cls._get_timezone(patient_id)
        records = list(TrackRecord.objects.filter(user__patient_id__exact=patient_id))
        for record in records:
            record.track_date = timezone.to_local(record.track_date, tz)
        return records

    @classmethod
    def get_range_with_timezone(cls, patient_id, start_date='', end_date=''):
        tz = cls._get_timezone(patient_id)
        start_date = cls._parse_to_utc(start_date, tz)
        end_date = cls._parse_to_utc(end_date, tz)

        if start_date is None and end_date is None:
            return cls.get_with_timezone(patient_id)

        if start_date is not None and end_date is not None:
            records = list(TrackRecord.objects.filter(user__patient_id__exact=patient_id).filter(
                track_date__range=(start_date, end_date)))
        elif start_date is not None:
            records = list(TrackRecord.objects.filter(user__patient_id__exact=patient_id).filter(
                track_date__gte=start_date))
        else:
            records = list(TrackRecord.objects.filter(user__patient_id__exact=patient_id).filter(
                track_date__lte=end_date))

        for record in records:
            record.track_date = timezone.to_local(record.track_date, tz)
        return records
