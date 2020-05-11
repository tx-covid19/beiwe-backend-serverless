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

from database.info_models import CovidCase

info_api = Blueprint('info_api', __name__)


def map_zipcode_to_county(zipcode: str):
    matching = zipcodes.matching(zipcode)
    if matching:
        res = matching[0]
        county, state = res['county'].rsplit(' ', 1)[0], res['state']
        state = getattr(us.states, res['state']).name
        return county, state
    else:
        return None, None


@info_api.route('/covid19', methods=['GET'])
@jwt_required
def get_covid_cases():
    try:
        latest_data = CovidCase.objects.latest('updated_time')
        region_data: dict = json.loads(latest_data.region_data)
    except:
        return jsonify({'msg': 'No data found.'})

    zipcode = request.args.get('zipcode', '')
    if zipcode:
        county, state = map_zipcode_to_county(zipcode)
        if county is None or state is None:
            return jsonify({'msg': 'zipcode not found.'})
        else:
            state_data = {
                k: sum(
                    county_data.get(k, 0)
                    for county_data in region_data[state].values()
                ) for k in ['confirmed', 'deaths', 'recovered', 'active']
            }
            return jsonify({
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
            })
    else:
        return jsonify({
            'latest_update': latest_data.updated_time,
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


@info_api.route('/refresh', methods=['GET'])
def refresh_data():
    try:
        # find the latest file in JHU dataset
        g = Github()
        repo = g.get_repo('CSSEGISandData/COVID-19')
        contents = repo.get_contents('csse_covid_19_data/csse_covid_19_daily_reports')
        contents = [x for x in contents if x.name.endswith('.csv')]
        contents.sort(key=lambda x: x.last_modified)
        file = contents[-1]

        # US country-level
        us_confirmed, us_recovered, us_deaths = usa_country_wide()

        stream = urllib.request.urlopen(file.download_url)
        csvfile = csv.reader(codecs.iterdecode(stream, 'utf-8'))
        last_update = ''

        region_data = defaultdict(dict)
        for row in csvfile:
            county, state, country = row[1], row[2], row[3]

            if country != 'US':
                continue

            # Skip the first line
            if county == 'Admin2':
                continue

            last_update = dateutil.parser.isoparse(row[4])
            confirmed = int(row[7])
            deaths = int(row[8])
            recovered = int(row[9])
            active = int(row[10])

            region_data[state][county] = {
                'confirmed': confirmed,
                'deaths': deaths,
                'recovered': recovered,
                'active': active
            }

        try:
            CovidCase(updated_time=last_update,
                      country_confirmed=us_confirmed,
                      country_recovered=us_recovered,
                      country_deaths=us_deaths,
                      region_data=json.dumps(region_data)).save()
        except:
            # has record with the same updated time
            pass

        return jsonify({'msg': 'Refreshed'})
    except:
        return jsonify({'msg': 'Refresh failed.'})
