from datetime import datetime

import dateutil
import iso3166
import requests
from django.contrib.postgres.fields import JSONField
from django.db import models

from config.constants import COVID_SUPPORTED_COUNTRIES


def endpoint(country_code, zipcode):
    API_KEY = ''
    return f'https://api.openweathermap.org/data/2.5/weather?zip={zipcode},{country_code}&appid={API_KEY}&units=metric'


def is_us(country):
    return country in ['United States', 'United States of America']


def save_weather(country: str, zipcode):
    if is_us(country):
        country_code = 'us'
    else:
        # must use country code as weather API requests
        country_code = iso3166.countries_by_name[country.upper()].alpha2.lower()

    try:
        r = requests.get(endpoint(country_code, zipcode), timeout=30)
        data = r.json()
        weather = data['weather'][0]['main']
        temperature = data['main']['temp']
        humidity = data['main']['humidity']
        updated_time = datetime.utcfromtimestamp(int(data['dt']))
        Weather(last_updated=updated_time, country=country, zipcode=zipcode, weather=weather, temperature=temperature,
                humidity=humidity).save()
        return True
    except:
        return False


def save_pollen(country, zipcode):
    if not is_us(country):
        return False
    headers = {
        "Content-Type": "application/json",
        "Referer": "https://www.pollen.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) "
                      + "AppleWebKit/537.36 (KHTML, like Gecko) "
                      + "Chrome/65.0.3325.181 Safari/537.36"
    }
    try:
        r = requests.get(f'https://www.pollen.com/api/forecast/current/pollen/{zipcode}', headers=headers, timeout=30)
        data = r.json()
        forecast_date = dateutil.parser.isoparse(data['ForecastDate'])
        today_data = data['Location']['periods'][1]
        today_index = today_data['Index']
        today_pollens = str([trigger['Name'] for trigger in today_data['Triggers']])
        Pollen(last_updated=forecast_date, country=country, zipcode=zipcode, index=today_index,
               pollens=today_pollens).save()
        return True
    except Exception:
        return False


class AbstractLocationInfo(models.Model):
    last_updated = models.DateTimeField()
    country = models.CharField(max_length=50)
    zipcode = models.CharField(max_length=20)

    class Meta:
        abstract = True
        unique_together = (("last_updated", "country", "zipcode"),)


class Weather(AbstractLocationInfo):
    weather = models.CharField(max_length=50)
    temperature = models.FloatField()
    humidity = models.IntegerField()

    @classmethod
    def latest_record(cls, country, zipcode, again=False):
        try:
            records = Weather.objects.filter(country__exact=country).filter(zipcode__exact=zipcode)
            if records.exists():
                return records.latest('last_updated')
            else:
                if again:
                    return None
                else:
                    save_weather(country, zipcode)
                    return cls.latest_record(country, zipcode, again=True)
        except:
            return None


class Pollen(AbstractLocationInfo):
    index = models.FloatField()
    pollens = models.CharField(max_length=100)

    @classmethod
    def latest_record(cls, country, zipcode, again=False):
        try:
            records = Pollen.objects.filter(country__exact=country).filter(zipcode__exact=zipcode)
            if records.exists():
                return records.latest('last_updated')
            else:
                if again:
                    return None
                else:
                    save_pollen(country, zipcode)
                    return cls.latest_record(country, zipcode, again=True)
        except:
            return None


class CovidCase(models.Model):
    updated_time = models.DateTimeField()
    country = models.CharField(max_length=25, choices=COVID_SUPPORTED_COUNTRIES)
    country_confirmed = models.PositiveIntegerField()
    country_recovered = models.PositiveIntegerField()
    country_deaths = models.PositiveIntegerField()
    region_data = JSONField()

    class Meta:
        unique_together = ('updated_time', 'country',)
