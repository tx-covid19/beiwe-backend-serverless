import codecs
import csv
import json
import urllib.request
from collections import defaultdict

import dateutil.parser
import requests
import us
import zipcodes
from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    jwt_required
)
from github import Github

from config.constants import COVID_SUPPORTED_COUNTRIES
from database.info_models import CovidCase

info_api = Blueprint('info_api', __name__)


def map_zipcode_to_county(zipcode: str):
    try:
        matching = zipcodes.matching(zipcode)
    except:
        return None, None

    if matching:
        res = matching[0]
        county, state = res['county'].rsplit(' ', 1)[0], res['state']
        state = getattr(us.states, res['state']).name
        return county, state
    else:
        return None, None


def get_latest_file_url(repo_path, folder_path, suffix):
    try:
        g = Github()
        repo = g.get_repo(repo_path)
        contents = repo.get_contents(folder_path)
    except:
        return ''

    contents = [x for x in contents if x.name.endswith('.' + suffix)]
    contents.sort(key=lambda x: x.last_modified)
    if contents:
        file = contents[-1]
        return file.download_url
    else:
        return ''


def get_travis_data():
    url = get_latest_file_url('tx-covid19/Austin-COVID19', '', 'json')
    try:
        r = requests.get(url, timeout=30)
        data = r.json()
        return data
    except:
        return {}


@info_api.route('/covid19', methods=['GET'])
@jwt_required
def get_covid_cases():
    country = request.args.get('country', 'us')
    region = request.args.get('state', '')
    zipcode = request.args.get('zipcode', '')

    supported_countries = dict(COVID_SUPPORTED_COUNTRIES)
    if country not in supported_countries:
        return jsonify({'msg': 'Country not found.'}), 404

    try:
        latest_data = CovidCase.objects.filter(country=country).latest('updated_time')
        region_data: dict = json.loads(latest_data.region_data)
    except:
        return jsonify({'msg': 'No data found.'}), 403

    if country == 'us' and zipcode:
        travis_data = get_travis_data()
        county, state = map_zipcode_to_county(zipcode)
        if county is None or state is None:
            return jsonify({'msg': 'zipcode not found.'}), 404
        else:
            state_data = {
                k: sum(
                    county_data.get(k, 0)
                    for county_data in region_data[state].values()
                ) for k in ['confirmed', 'deaths', 'recovered', 'active']
            }
            res = {
                'latest_update': latest_data.updated_time,
                'country': {
                    'name': 'United States of America',
                    'confirmed': latest_data.country_confirmed,
                    'deaths': latest_data.country_deaths,
                    'recovered': latest_data.country_recovered,
                },
                'state': {
                    'name': state,
                    **state_data
                },
                'county': {
                    'name': county,
                    **region_data[state][county],
                }
            }

            if zipcode in travis_data:
                res['zipcode'] = {
                    'confirmed': travis_data[zipcode]
                }

            return jsonify(res)

    elif region != '':
        if region in region_data:
            region_data = region_data[region]
        res = {
            'latest_update': latest_data.updated_time,
            'country': {
                'name': supported_countries[country],
                'confirmed': latest_data.country_confirmed,
                'deaths': latest_data.country_deaths,
                'recovered': latest_data.country_recovered,
            },
            'state': {
                'name': region,
                **region_data
            },
        }
        return jsonify(res)

    else:
        return jsonify({
            'latest_update': latest_data.updated_time,
            'name': supported_countries[country],
            'country': {
                'confirmed': latest_data.country_confirmed,
                'recovered': latest_data.country_recovered,
                'deaths': latest_data.country_deaths,
            },
            'data': region_data,
        })


def usa_country_wide():
    try:
        r = requests.get('https://covid19.mathdro.id/api/countries/us', timeout=30)
        data = r.json()
        return (
            int(data['confirmed']['value']),
            int(data['recovered']['value']),
            int(data['deaths']['value'])
        )
    except:
        return 0, 0, 0


def canada_country_wide():
    try:
        r = requests.get('https://covid19.mathdro.id/api/countries/canada', timeout=30)
        data = r.json()
        return (
            int(data['confirmed']['value']),
            int(data['recovered']['value']),
            int(data['deaths']['value'])
        )
    except:
        return 0, 0, 0


def update_brazil():
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
        recovered = int(br_data['recovered'])
        res_dict = defaultdict(dict)
        for dt in br_data['infectedByRegion']:
            state, local_total = dt['state'], int(dt['count'])
            res_dict[state]['total'] = local_total

        for dt in br_data['deceasedByRegion']:
            state, local_deaths = dt['state'], int(dt['count'])
            res_dict[state]['deaths'] = local_deaths

        CovidCase(updated_time=last_updated, country='br',
                  country_confirmed=total, country_deaths=deaths, country_recovered=recovered,
                  region_data=json.dumps(res_dict)).save()
    except:
        pass


def update_mexico():
    try:
        r = requests.get(
            'https://api.apify.com/v2/key-value-stores/vpfkeiYLXPIDIea2T/records/LATEST?disableRedirect=true',
            timeout=30)
        mx_data = r.json()
        last_updated = dateutil.parser.isoparse(mx_data['lastUpdatedAtSource'])
        total = int(mx_data['infected'])
        deaths = int(mx_data['deceased'])
        # no data point
        recovered = 0

        CovidCase(updated_time=last_updated, country='mx',
                  country_confirmed=total, country_deaths=deaths, country_recovered=recovered,
                  region_data=json.dumps(mx_data['State'])).save()
    except:
        pass


@info_api.route('/refresh', methods=['GET'])
def refresh_data():
    try:
        # US country-level
        us_confirmed, us_recovered, us_deaths = usa_country_wide()
        ca_confirmed, ca_recovered, ca_deaths = canada_country_wide()

        jhu_file_url = get_latest_file_url('CSSEGISandData/COVID-19', 'csse_covid_19_data/csse_covid_19_daily_reports',
                                           'csv')
        stream = urllib.request.urlopen(jhu_file_url)
        csvfile = csv.reader(codecs.iterdecode(stream, 'utf-8'))
        last_update = ''

        us_region_data = defaultdict(dict)
        ca_region_data = {}
        for row in csvfile:
            county, state, country = row[1], row[2], row[3]
            # Skip the first line header
            if county == 'Admin2':
                continue

            last_update = dateutil.parser.isoparse(row[4])
            confirmed = int(row[7])
            deaths = int(row[8])
            recovered = int(row[9])
            active = int(row[10])

            if country == 'US':
                us_region_data[state][county] = {
                    'confirmed': confirmed,
                    'deaths': deaths,
                    'recovered': recovered,
                    'active': active
                }

            elif country == 'Canada':
                ca_region_data[state] = {
                    'confirmed': confirmed,
                    'deaths': deaths,
                    'recovered': recovered,
                    'active': active
                }

        update_mexico()
        update_brazil()

        try:
            CovidCase(updated_time=last_update,
                      country='us',
                      country_confirmed=us_confirmed,
                      country_recovered=us_recovered,
                      country_deaths=us_deaths,
                      region_data=json.dumps(us_region_data)).save()
            CovidCase(updated_time=last_update,
                      country='ca',
                      country_confirmed=ca_confirmed,
                      country_recovered=ca_recovered,
                      country_deaths=ca_deaths,
                      region_data=json.dumps(ca_region_data)).save()
        except:
            # has record with the same updated time
            return jsonify({'msg': 'Record exists.'})

        return jsonify({'msg': 'Refreshed.'})
    except:
        return jsonify({'msg': 'Refresh failed.'})
