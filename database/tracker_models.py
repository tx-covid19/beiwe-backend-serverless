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

    def save(self, *args, **kwargs):
        patient_id = self.user.patient_id
        tz = self._get_timezone(patient_id)
        self.track_date = timezone.to_utc(datetime.strptime(self.track_date, '%Y-%m-%d %H:%M:%S'), tz)
        super(TrackRecord, self).save()

    @classmethod
    def get_with_timezone(cls, patient_id):
        tz = cls._get_timezone(patient_id)
        records = list(TrackRecord.objects.filter(user__patient_id__exact=patient_id))
        for record in records:
            record.track_date = timezone.to_local(record.track_date, tz)
        return records
