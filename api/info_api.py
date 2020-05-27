import codecs
import csv
import json
import urllib.request
from collections import defaultdict
import os
import datetime
import dateutil.parser
import requests
import us
import zipcodes

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from database.info_models import CovidCases, AdministrativeDivision, AdministrativeLevel
from config.geo_constants import US_STATE_ABBRS


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
        return jsonify({'msg': 'No data found.'}), 403

    zipcode = request.args.get('zipcode', '')
    travis_data = get_travis_data()
    if zipcode:
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
                    'abbr': 'US',
                    'confirmed': latest_data.country_confirmed,
                    'deaths': latest_data.country_deaths,
                    'recovered': latest_data.country_recovered,
                },
                'state': {
                    'name': state,
                    'abbr': US_STATE_ABBRS[state.strip()],
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
