from datetime import datetime

from dateutil.tz import gettz
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import F, Func
from django.utils.timezone import localtime

from config.constants import ResearcherRole
from config.study_constants import (ABOUT_PAGE_TEXT, CONSENT_FORM_TEXT,
    DEFAULT_CONSENT_SECTIONS_JSON, SURVEY_SUBMIT_SUCCESS_TOAST_TEXT)
from database.models import JSONTextField, TimestampedModel
from database.tableau_api_models import ForestParam
from database.user_models import Researcher
from database.validators import LengthValidator


class Study(TimestampedModel):
    # When a Study object is created, a default DeviceSettings object is automatically
    # created alongside it. If the Study is created via the researcher interface (as it
    # usually is) the researcher is immediately shown the DeviceSettings to edit. The code
    # to create the DeviceSettings object is in database.signals.populate_study_device_settings.

    name = models.TextField(unique=True, help_text='Name of the study; can be of any length')
    encryption_key = models.CharField(
        max_length=32, validators=[LengthValidator(32)],
        help_text='Key used for encrypting the study data'
    )
    object_id = models.CharField(
        max_length=24, unique=True, validators=[LengthValidator(24)],
        help_text='ID used for naming S3 files'
    )
    is_test = models.BooleanField(default=True)
    timezone_name = models.CharField(  # Warning: this is going to be deleted.
        max_length=256, default="America/New_York", null=False, blank=False
    )
    deleted = models.BooleanField(default=False)
    
    forest_enabled = models.BooleanField(default=False)
    # Note: this is not nullable to prevent bugs where this is null, though if forest_enabled is
    #       False, the forest_param field isn't used
    forest_param = models.ForeignKey(ForestParam, on_delete=models.PROTECT)

    def save(self, *args, **kwargs):
        """ Ensure there is a study device settings attached to this study. """
        # First we just save. This code has vacillated between throwing a validation error and not
        # during study creation.  Our current fix is to save, then test whether a device settings
        # object exists.  If not, create it.
        try:
            self.forest_param
        except ObjectDoesNotExist:
            self.forest_param = ForestParam.objects.get(default=True)
        super().save(*args, **kwargs)
        try:
            self.device_settings
        except ObjectDoesNotExist:
            settings = DeviceSettings(study=self)
            self.device_settings = settings
            settings.save()
            # update the study object to have a device settings object (possibly unnecessary?).
            super().save(*args, **kwargs)



    @classmethod
    def create_with_object_id(cls, **kwargs):
        """ Creates a new study with a populated object_id field. """
        study = cls(object_id=cls.generate_objectid_string("object_id"), **kwargs)
        study.save()
        return study

    @classmethod
    def get_all_studies_by_name(cls):
        """ Sort the un-deleted Studies a-z by name, ignoring case. """
        return (cls.objects
                .filter(deleted=False)
                .annotate(name_lower=Func(F('name'), function='LOWER'))
                .order_by('name_lower'))

    @classmethod
    def _get_administered_studies_by_name(cls, researcher):
        return cls.get_all_studies_by_name().filter(
                study_relations__researcher=researcher,
                study_relations__relationship=ResearcherRole.study_admin,
            )

    @classmethod
    def get_researcher_studies_by_name(cls, researcher):
        return cls.get_all_studies_by_name().filter(study_relations__researcher=researcher)

    def get_survey_ids_and_object_ids(self, survey_type='tracking_survey'):
        return self.surveys.filter(survey_type=survey_type, deleted=False).values_list('id', 'object_id')

    def get_researchers(self):
        return Researcher.objects.filter(study_relations__study=self)

    # We override the as_unpacked_native_python function to not include the encryption key.
    def as_unpacked_native_python(self, remove_timestamps=True):
        ret = super().as_unpacked_native_python(remove_timestamps=remove_timestamps)
        ret.pop("encryption_key")
        return ret

    def notification_events(self, **archived_event_filter_kwargs):
        from database.schedule_models import ArchivedEvent
        return ArchivedEvent.objects.filter(
            survey_archive_id__in=self.surveys.all().values_list("archives__id", flat=True)
        ).filter(**archived_event_filter_kwargs).order_by("-scheduled_time")

    def now(self) -> datetime:
        """ Returns a timezone.now() equivalence in the study's timezone. """
        return localtime(localtime(), timezone=self.timezone)  # localtime(localtime(... saves an import... :D

    @property
    def timezone(self):
        """ So pytz.timezone("America/New_York") provides a tzinfo-like object that is wrong by 4
        minutes.  That's insane.  The dateutil gettz function doesn't have that fun insanity. """
        return gettz(self.timezone_name)


class StudyField(models.Model):
    study = models.ForeignKey(Study, on_delete=models.PROTECT, related_name='fields')
    field_name = models.TextField()

    class Meta:
        unique_together = (("study", "field_name"),)


class DeviceSettings(TimestampedModel):
    """
    The DeviceSettings database contains the structure that defines
    settings pushed to devices of users in of a study.
    """

    # Whether various device options are turned on
    accelerometer = models.BooleanField(default=True)
    gps = models.BooleanField(default=True)
    calls = models.BooleanField(default=True)
    texts = models.BooleanField(default=True)
    wifi = models.BooleanField(default=True)
    bluetooth = models.BooleanField(default=False)
    power_state = models.BooleanField(default=True)
    use_anonymized_hashing = models.BooleanField(default=True)
    use_gps_fuzzing = models.BooleanField(default=False)
    call_clinician_button_enabled = models.BooleanField(default=True)
    call_research_assistant_button_enabled = models.BooleanField(default=True)

    # Whether iOS-specific data streams are turned on
    proximity = models.BooleanField(default=False)
    gyro = models.BooleanField(default=False)
    magnetometer = models.BooleanField(default=False)
    devicemotion = models.BooleanField(default=False)
    reachability = models.BooleanField(default=True)

    # Upload over cellular data or only over WiFi (WiFi-only is default)
    allow_upload_over_cellular_data = models.BooleanField(default=False)

    # Timer variables
    accelerometer_off_duration_seconds = models.PositiveIntegerField(default=10)
    accelerometer_on_duration_seconds = models.PositiveIntegerField(default=10)
    bluetooth_on_duration_seconds = models.PositiveIntegerField(default=60)
    bluetooth_total_duration_seconds = models.PositiveIntegerField(default=300)
    bluetooth_global_offset_seconds = models.PositiveIntegerField(default=0)
    check_for_new_surveys_frequency_seconds = models.PositiveIntegerField(default=3600 * 6)
    create_new_data_files_frequency_seconds = models.PositiveIntegerField(default=15 * 60)
    gps_off_duration_seconds = models.PositiveIntegerField(default=600)
    gps_on_duration_seconds = models.PositiveIntegerField(default=60)
    seconds_before_auto_logout = models.PositiveIntegerField(default=600)
    upload_data_files_frequency_seconds = models.PositiveIntegerField(default=3600)
    voice_recording_max_time_length_seconds = models.PositiveIntegerField(default=240)
    wifi_log_frequency_seconds = models.PositiveIntegerField(default=300)

    # iOS-specific timer variables
    gyro_off_duration_seconds = models.PositiveIntegerField(default=600)
    gyro_on_duration_seconds = models.PositiveIntegerField(default=60)
    magnetometer_off_duration_seconds = models.PositiveIntegerField(default=600)
    magnetometer_on_duration_seconds = models.PositiveIntegerField(default=60)
    devicemotion_off_duration_seconds = models.PositiveIntegerField(default=600)
    devicemotion_on_duration_seconds = models.PositiveIntegerField(default=60)

    # Text strings
    about_page_text = models.TextField(default=ABOUT_PAGE_TEXT)
    call_clinician_button_text = models.TextField(default='Call My Clinician')
    consent_form_text = models.TextField(default=CONSENT_FORM_TEXT)
    survey_submit_success_toast_text = models.TextField(default=SURVEY_SUBMIT_SUCCESS_TOAST_TEXT)

    # Consent sections
    consent_sections = JSONTextField(default=DEFAULT_CONSENT_SECTIONS_JSON)

    study = models.OneToOneField('Study', on_delete=models.PROTECT, related_name='device_settings')
