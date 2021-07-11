# Generated by Django 2.2.11 on 2020-05-18 19:08

from django.db import migrations

from database.survey_models import Survey


def backfill_missing_survey_archives(*args, **kwargs):
    """ We need to fill SurveyArchive objects for all surveys predating its existence. """
    for survey in Survey.objects.filter(archives__isnull=True):
        # SurveyArchives are created and tested in the save trigger.
        survey.save()


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0034_auto_20200506_2212'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='surveyarchive',
            name='archive_end',
        ),
        migrations.RemoveField(
            model_name='surveyarchive',
            name='study',
        ),
        migrations.RunPython(backfill_missing_survey_archives, reverse_code=migrations.RunPython.noop),
    ]
