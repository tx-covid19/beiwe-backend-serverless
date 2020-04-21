import codecs
import csv
import urllib.request
from collections import defaultdict
from datetime import datetime
from typing import List, Dict
import dateutil.parser

import iso3166
import requests
import us
import zipcodes
from django.db import models
from github import Github


def endpoint(country_code, zipcode):
    API_KEY = ''
    return f'https://api.openweathermap.org/data/2.5/weather?zip={zipcode},{country_code}&appid={API_KEY}&units=metric'


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
        forecast_date = datetime.fromisoformat(data['ForecastDate'])
        today_data = data['Location']['periods'][1]
        today_index = today_data['Index']
        today_pollens = str([trigger['Name'] for trigger in today_data['Triggers']])
        Pollen(last_updated=forecast_date, country=country, zipcode=zipcode, index=today_index,
               pollens=today_pollens).save()
        return True
    except Exception:
        return False


def canada_country_wide():
    try:
        r = requests.get('https://covid19.mathdro.id/api/countries/canada', timeout=30)
        data = r.json()
        return int(data['confirmed']['value']), int(data['deaths']['value'])
    except:
        return 0, 0


def usa_country_wide():
    try:
        r = requests.get('https://covid19.mathdro.id/api/countries/us', timeout=30)
        data = r.json()
        return int(data['confirmed']['value']), int(data['deaths']['value'])
    except:
        return 0, 0


def brazil_detail():
    mapping = {
        'AC': 'Acre',
        'AL': 'Alagoas',
        'AP': 'Amapá',
        'AM': 'Amazonas',
        'BA': 'Bahia',
        'CE': 'Ceará',
        'DF': 'Distrito Federal',
        'ES': 'Espírito Santo',
        'GO': 'Goiás',
        'MA': 'Maranhão',
        'MT': 'Mato Grosso',
        'MS': 'Mato Grosso do Sul',
        'MG': 'Minas Gerais',
        'PR': 'Paraná',
        'PB': 'Paraíba',
        'PA': 'Pará',
        'PE': 'Pernambuco',
        'PI': 'Piauí',
        'RN': 'Rio Grande do Norte',
        'RS': 'Rio Grande do Sul',
        'RJ': 'Rio de Janeiro',
        'RO': 'Rondônia',
        'RR': 'Roraima',
        'SC': 'Santa Catarina',
        'SE': 'Sergipe',
        'SP': 'São Paulo',
        'TO': 'Tocantins'
    }
    try:
        r = requests.get(
            'https://api.apify.com/v2/key-value-stores/TyToNta7jGKkpszMZ/records/LATEST?disableRedirect=true',
            timeout=30)
        br_data = r.json()
        last_updated = dateutil.parser.isoparse(br_data['lastUpdatedAtSource'])
        total = int(br_data['infected'])
        deaths = int(br_data['deceased'])
        res_dict = defaultdict(dict)
        for dt in br_data['infectedByRegion']:
            state, local_total = dt['state'], int(dt['count'])
            res_dict[state]['total'] = local_total

        for dt in br_data['deceasedByRegion']:
            state, local_deaths = dt['state'], int(dt['count'])
            res_dict[state]['deaths'] = local_deaths

        for k, v in res_dict.items():
            CovidCase(last_updated=last_updated, country='Brazil', state=mapping[k],
                      nation_total=total,
                      nation_deaths=deaths, local_total=v['total'],
                      local_deaths=v['deaths']).save()
    except:
        pass


def map_to_county_level(info_list: List[Dict], state_full_name=False):
    info_list = info_list
    geo_dict = defaultdict(list)
    for info in info_list:
        country, zipcode = info['country'], info['zipcode']
        if not is_us(country):
            continue
        matching = zipcodes.matching(zipcode)
        if matching:
            res = matching[0]
            county, state = res['county'].split(' ')[0], res['state']
            if state_full_name:
                state = getattr(us.states, res['state']).name
            geo_dict[(county, state)].append((country, zipcode))
    return geo_dict


def save_covid(info_list):
    county_dict = map_to_county_level(info_list, state_full_name=True)

    try:
        # find the latest file in JHU dataset
        g = Github()
        repo = g.get_repo('CSSEGISandData/COVID-19')
        contents = repo.get_contents('csse_covid_19_data/csse_covid_19_daily_reports')
        contents = [x for x in contents if x.name.endswith('csv')]
        contents.sort(key=lambda x: x.last_modified)
        file = contents[-1]

        country_stat = {}

        # Canada country-level
        ca_total, ca_deaths = canada_country_wide()
        country_stat['Canada'] = {
            'total': ca_total,
            'deaths': ca_deaths
        }

        # US country-level
        us_total, us_deaths = usa_country_wide()
        country_stat['US'] = {
            'total': us_total,
            'deaths': us_deaths
        }

        stream = urllib.request.urlopen(file.download_url)
        csvfile = csv.reader(codecs.iterdecode(stream, 'utf-8'))

        for row in csvfile:
            county, state, country = row[1], row[2], row[3]

            # Skip the first line
            if county == 'Admin2':
                continue

            last_update = datetime.fromisoformat(row[4])
            confirmed = int(row[7])
            deaths = int(row[8])

            if country == 'US' and (county, state) in county_dict:
                # Search US by counties
                for country, zipcode in county_dict[(county, state)]:
                    CovidCase(last_updated=last_update, country=country, zipcode=zipcode,
                              nation_total=country_stat['US']['total'],
                              nation_deaths=country_stat['US']['deaths'], local_total=confirmed,
                              local_deaths=deaths).save()
            elif country == 'Canada':
                # Save all Canada province data
                CovidCase(last_updated=last_update, country=country, state=state,
                          nation_total=country_stat['Canada']['total'],
                          nation_deaths=country_stat['Canada']['deaths'], local_total=confirmed,
                          local_deaths=deaths).save()
            elif country == 'Mexico':
                # Save total, need other sources for detail
                country_stat[country] = {
                    'total': confirmed,
                    'deaths': deaths
                }
            elif state == 'Puerto Rico':
                # Count it as a single dt point
                CovidCase(last_updated=last_update, country=state, state=state,
                          nation_total=confirmed,
                          nation_deaths=deaths, local_total=confirmed, local_deaths=deaths).save()

        # Let Brazil in
        brazil_detail()

    except:
        pass


class AbstractLocationInfo(models.Model):
    last_updated = models.DateTimeField()
    country = models.CharField(max_length=20)
    zipcode = models.CharField(max_length=20)

    class Meta:
        abstract = True
        unique_together = (("last_updated", "country", "zipcode"),)


class CovidCase(AbstractLocationInfo):
    state = models.CharField(max_length=50, blank=True, null=True)
    zipcode = models.CharField(max_length=20, blank=True, null=True)
    nation_total = models.PositiveIntegerField()
    nation_deaths = models.PositiveIntegerField()
    local_total = models.PositiveIntegerField()
    local_deaths = models.PositiveIntegerField()

    @classmethod
    def latest_record(cls, country, state, zipcode, again=False):
        try:
            if country == 'United States':
                records = CovidCase.objects.filter(country__exact=country).filter(zipcode__exact=zipcode)
            else:
                records = CovidCase.objects.filter(country__exact=country).filter(state__exact=state)

            if records.exists():
                return records.latest('last_updated')
            else:
                if again:
                    return None
                else:
                    save_covid([{
                        'country': country,
                        'state': state,
                        'zipcode': zipcode
                    }])
                    return cls.latest_record(country, state, zipcode, again=True)
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
