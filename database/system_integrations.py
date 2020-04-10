from datetime import timedelta
from time import sleep

from django.db import models
from django.utils import timezone

from config.constants import UPLOAD_FILE_TYPE_MAPPING
from libs.security import decode_base64
from database.models import JSONTextField, AbstractModel, Participant, Researcher

class BoxIntegration(AbstractModel):
   
    researcher = models.OneToOneField(Researcher, on_delete=models.PROTECT, related_name='box_integration', primary_key=True)
    access_token = models.CharField(max_length=256)
    refresh_token = models.CharField(max_length=256)
    write_to_directory = models.CharField(max_length=256, blank=True)

    def store_box_tokens(self, access_token, refresh_token):

        self.access_token = access_token
        self.refresh_token = refresh_token
        self.save()
