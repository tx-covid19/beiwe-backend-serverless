# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2018-04-13 20:33
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0006_auto_20180411_0453'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pipelineuploadtags',
            name='tag',
            field=models.TextField(),
        ),
    ]