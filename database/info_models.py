import codecs
import csv
import urllib.request
from collections import defaultdict
from datetime import datetime
from typing import List, Dict

import iso3166
import requests
import us
import zipcodes
from django.db import models
from github import Github


def endpoint(country_code, zipcode):
    API_KEY = '398251854a8f55b4c8ebe63e1ad9063b'  # has been revoked :)
    return f'https://api.openweathermap.org/data/2.5/weather?zip={zipcode},{country_code}&appid={API_KEY}'


def is_us(country):
    return country in ['United States', 'United States of America']


def save_weather(country: str, zipcode):
    if is_us(country):
        country_code = 'us'
    else:
        country_code = iso3166.countries_by_name[country.upper()].alpha2.lower()

    try:
        r = requests.get(endpoint(country_code, zipcode), timeout=30)
        data = r.json()
        weather = data['weather'][0]['main']
        temperature = data['main']['temp']  # Kevin
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
        forecast_date = datetime.fromisoformat(data['ForecastDate']).strftime("%Y-%m-%d %H:%M:%S")
        today_data = data['Location']['periods'][1]
        today_index = today_data['Index']
        today_pollens = str([trigger['Name'] for trigger in today_data['Triggers']])
        Pollen(last_updated=forecast_date, country=country, zipcode=zipcode, index=today_index,
               pollens=today_pollens).save()
        return True
    except Exception:
        return False


def map_to_county(zipcode_list: List[Dict], state_full_name=False):
    info_list = zipcode_list
    geo_dict = defaultdict(list)
    other_countries = defaultdict(list)
    for info in info_list:
        country, zipcode = info['country'], info['zipcode']
        if not is_us(country):
            other_countries[country].append((country, zipcode))
            continue
        matching = zipcodes.matching(zipcode)
        if matching:
            res = matching[0]
            county, state = res['county'].split(' ')[0], res['state']
            if state_full_name:
                state = getattr(us.states, res['state']).name
            geo_dict[(county, state)].append((country, zipcode))
    return geo_dict, other_countries


def save_covid(info_list):
    geo_dict, other_countries = map_to_county(info_list, state_full_name=True)

    count = 0
    try:
        g = Github()
        repo = g.get_repo('CSSEGISandData/COVID-19')
        contents = repo.get_contents('csse_covid_19_data/csse_covid_19_daily_reports')
        contents = [x for x in contents if x.name.endswith('csv')]
        contents.sort(key=lambda x: x.last_modified)
        file = contents[-1]

        stream = urllib.request.urlopen(file.download_url)
        csvfile = csv.reader(codecs.iterdecode(stream, 'utf-8'))

        for row in csvfile:
            county, state, country = row[1], row[2], row[3]
            if county == 'Admin2':
                continue
            last_update = datetime.fromisoformat(row[4])
            confirmed = int(row[7])
            deaths = int(row[8])
            if (county, state) in geo_dict:
                for country, zipcode in geo_dict[(county, state)]:
                    CovidCase(last_updated=last_update, country=country, zipcode=zipcode, nation_total=confirmed,
                              nation_deaths=deaths, local_total=confirmed, local_deaths=deaths).save()
                    count += 1
            elif country in other_countries:
                for country, zipcode in other_countries[country]:
                    CovidCase(last_updated=last_update, country=country, zipcode=zipcode, nation_total=confirmed,
                              nation_deaths=deaths, local_total=0, local_deaths=0).save()
                    count += 1
    except:
        pass

    return count, len(info_list)


class AbstractLocationInfo(models.Model):
    last_updated = models.DateTimeField()
    country = models.CharField(max_length=20)
    zipcode = models.CharField(max_length=20)

    class Meta:
        abstract = True
        unique_together = (("last_updated", "country", "zipcode"),)


class CovidCase(AbstractLocationInfo):
    nation_total = models.PositiveIntegerField()
    nation_deaths = models.PositiveIntegerField()
    local_total = models.PositiveIntegerField()
    local_deaths = models.PositiveIntegerField()

    @classmethod
    def latest_record(cls, country, zipcode, again=False):
        try:
            records = CovidCase.objects.filter(country__exact=country).filter(zipcode__exact=zipcode)
            if records.exists():
                return records.latest('last_updated')
            else:
                if again:
                    return None
                else:
                    save_covid([{
                        'country': country,
                        'zipcode': zipcode
                    }])
                    return cls.latest_record(country, zipcode, again=True)
        except:
            return None


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
