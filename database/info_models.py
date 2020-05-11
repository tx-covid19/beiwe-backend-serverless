from django.db import models

from database.common_models import AbstractModel, JSONTextField


class CovidCase(AbstractModel):
    updated_time = models.DateTimeField(unique=True)
    country_confirmed = models.PositiveIntegerField()
    country_recovered = models.PositiveIntegerField()
    country_deaths = models.PositiveIntegerField()
    region_data = JSONTextField()
