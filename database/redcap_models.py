from django.db import models

from .common_models import AbstractModel
from .study_models import Study
from .user_models import Participant


class RedcapRecord(models.Model):
    user = models.OneToOneField(Participant, on_delete=models.CASCADE)
    study = models.ForeignKey(Study, on_delete=models.CASCADE)
    record_id = models.CharField(max_length=50)

    class Meta:
        unique_together = ('study', 'record_id',)
