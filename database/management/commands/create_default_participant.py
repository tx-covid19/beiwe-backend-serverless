from django.core.management.base import BaseCommand
from database.user_models import Participant
from database.study_models import Study


class Command(BaseCommand):
    args = ""
    help = ""

    def handle(self, *args, **options):
        try:
            study = Study.create_with_object_id(name='Study 1', encryption_key='aabbccddeeffgghhiijjkkllmmnnoopp')
        except:
            study = Study.objects.get()
        new_participant = Participant.create(patient_id="aaaaaaaa", password="aaaaaaaa", study=study)
