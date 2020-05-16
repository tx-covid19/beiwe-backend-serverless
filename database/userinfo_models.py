from django.db import models

from .user_models import Participant


class ParticipantInfo(models.Model):
    SUPPORT_COUNTRIES = [
        ('United States', 'United States'),
        ('Canada', 'Canada'),
        ('Mexico', 'Mexico'),
        ('Brazil', 'Brazil'),
        ('Puerto Rico', 'Puerto Rico')
    ]

    user = models.OneToOneField(Participant, on_delete=models.CASCADE)

    country = models.CharField(max_length=100, choices=SUPPORT_COUNTRIES)
    # For Puerto Rico, country == state
    state = models.CharField(max_length=50)
    zipcode = models.CharField(max_length=20)

    # Pytz compatible
    timezone = models.CharField(max_length=100)
