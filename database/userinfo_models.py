from django.db import models

from .user_models import Participant


class ParticipantInfo(models.Model):
    user = models.OneToOneField(Participant, on_delete=models.PROTECT)

    country = models.CharField(max_length=100)
    zipcode = models.CharField(max_length=20)
    timezone = models.CharField(max_length=100)
    record_id = models.CharField(max_length=50)

    @classmethod
    def get_country_zipcode(cls, patient_id):
        info_set = ParticipantInfo.objects.filter(user__patient_id__exact=patient_id)
        if info_set.exists():
            return info_set.get().country, info_set.get().zipcode
        else:
            return None, None
