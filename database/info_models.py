from django.db import models

from database.common_models import AbstractModel, JSONTextField


class CovidCase(AbstractModel):
    updated_time = models.DateTimeField(unique=True)
    country_total = models.PositiveIntegerField()
    country_deaths = models.PositiveIntegerField()
    region_data = JSONTextField()
