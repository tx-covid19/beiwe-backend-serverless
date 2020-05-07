# -*- coding: utf-8 -*-
from django.db import migrations

from database.user_models import Researcher


def convert_batch_users(apps, schema_editor):
    for researcher in Researcher.objects.all():
        if researcher.username.startswith("BATCH USER"):
            researcher.is_batch_user = True
            researcher.save()

class Migration(migrations.Migration):
    dependencies = [
        ('database', '0023_auto_20191003_1928'),
    ]

    operations = [
        migrations.RunPython(convert_batch_users),
    ]
