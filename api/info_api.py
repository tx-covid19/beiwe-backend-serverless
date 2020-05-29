import codecs
import csv
import json
import urllib.request
from collections import defaultdict
import os
import datetime
import dateutil.parser
import requests
import zipcodes

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from database.info_models import CovidCases, AdministrativeDivision, AdministrativeLevel
from config.geo_constants import US_STATE_ABBRS, US_STATE_NAMES


info_api = Blueprint('info_api', __name__)


def map_zipcode_to_county(zipcode: str):
    matching = zipcodes.matching(zipcode)
    if matching:
        res = matching[0]
        county, state = res['county'].rsplit(' ', 1)[0], res['state']
        state = US_STATE_NAMES[res['state']]
        return county, state
    else:
        return None, None


@info_api.route('/covid19', methods=['GET'])
# @jwt_required
def get_covid_cases():

    country = AdministrativeDivision.objects.get(
        administrative_level=AdministrativeLevel.COUNTRY,
        identifier='United States of America',
    )
    country_cases = CovidCases.objects.filter(division=country).latest('date')

    country_data = {
        'name': country.identifier,
        'abbr': 'US',
        'confirmed': country_cases.confirmed,
        'recovered': country_cases.recovered,
        'deaths': country_cases.deaths,
        'date': country_cases.date.date().isoformat(),
    }

    zipcode = request.args.get('zipcode', '')
    if zipcode:
        county, state = map_zipcode_to_county(zipcode)

        if county is None or state is None:
            return jsonify({'msg': 'zipcode not found.'}), 404
        else:

            state = AdministrativeDivision.objects.get(
                parent=country,
                administrative_level=AdministrativeLevel.STATE,
                identifier=state,
            )
            state_cases = CovidCases.objects.filter(division=state).latest('date')

            county = AdministrativeDivision.objects.get(
                parent=state,
                administrative_level=AdministrativeLevel.COUNTY,
                identifier=county,
            )
            county_cases = CovidCases.objects.filter(division=county).latest('date')


            res = {
                'country': country_data,
                'state': {
                    'name': state.identifier,
                    'abbr': US_STATE_ABBRS[state.identifier],
                    'confirmed': state_cases.confirmed,
                    'recovered': state_cases.recovered,
                    'deaths': state_cases.deaths,
                    'date': state_cases.date.date().isoformat(),
                },
                'county': {
                    'name': county.identifier,
                    'confirmed': county_cases.confirmed,
                    'recovered': county_cases.recovered,
                    'deaths': county_cases.deaths,
                    'date': county_cases.date.date().isoformat(),
                }
            }

            return jsonify(res)
    else:
        return jsonify({
            'country': country_data,
        })


@info_api.route('/covid19/timeseries', methods=['GET'])
# @jwt_required
def get_covid_cases_timeseries():

    country = AdministrativeDivision.objects.get(
        administrative_level=AdministrativeLevel.COUNTRY,
        identifier='United States of America',
    )
    country_cases = CovidCases.objects.filter(division=country)
    country_timeseries = [
        {
            'date': cases.date.date().isoformat(),
            'confirmed': cases.confirmed,
            'recovered': cases.recovered,
            'deaths': cases.deaths
        }
        for cases in country_cases
    ]

    zipcode = request.args.get('zipcode', '')
    if zipcode:
        county, state = map_zipcode_to_county(zipcode)

        if county is None or state is None:
            return jsonify({'msg': 'zipcode not found.'}), 404
        else:

            state = AdministrativeDivision.objects.get(
                parent=country,
                administrative_level=AdministrativeLevel.STATE,
                identifier=state,
            )
            state_cases = CovidCases.objects.filter(division=state)
            state_timeseries = [
                {
                    'date': cases.date.date().isoformat(),
                    'confirmed': cases.confirmed,
                    'recovered': cases.recovered,
                    'deaths': cases.deaths
                }
                for cases in state_cases
            ]

            county = AdministrativeDivision.objects.get(
                parent=state,
                administrative_level=AdministrativeLevel.COUNTY,
                identifier=county,
            )
            county_cases = CovidCases.objects.filter(division=county)
            county_timeseries = [
                {
                    'date': cases.date.date().isoformat(),
                    'confirmed': cases.confirmed,
                    'recovered': cases.recovered,
                    'deaths': cases.deaths
                }
                for cases in county_cases
            ]

            res = {
                'country': {
                    'name': country.identifier,
                    'abbr': 'US',
                    'timeseries': country_timeseries,
                },
                'state': {
                    'name': state.identifier,
                    'abbr': US_STATE_ABBRS[state.identifier],
                    'timeseries': state_timeseries,
                },
                'county': {
                    'name': county.identifier,
                    'timeseries': county_timeseries,
                }
            }

            return jsonify(res)
    else:
        return jsonify({
            'country': country_timeseries,
        })
