from django.contrib.postgres.fields import JSONField
from django.db import models

from database.models import AbstractModel


class CovidCase(models.Model):
    timestamp = models.DateTimeField(auto_now=True)
    nation_total = models.PositiveIntegerField()
    nation_deaths = models.PositiveIntegerField()
    tx_total = models.PositiveIntegerField()
    tx_deaths = models.PositiveIntegerField()
    counties_json = JSONField()
