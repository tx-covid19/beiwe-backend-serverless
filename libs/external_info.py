import codecs
import csv
import json
import urllib.request
from collections import defaultdict
import os
import datetime

from database.info_models import CovidCases, AdministrativeDivision, AdministrativeLevel
from config.geo_constants import US_STATE_ABBRS

from github import Github


def refresh_data():

    country = AdministrativeDivision.objects.get_or_create(
        identifier='United States of America',
        administrative_level=AdministrativeLevel.COUNTRY,
    )
    country_counts = {
        'confirmed': 0,
        'deaths': 0,
        'recovered': 0,
    }
    states = {}
    states_counts = defaultdict(lambda: {
        'confirmed': 0,
        'deaths': 0,
        'recovered': 0,
    })
    counties = {}
    
    g = Github()
    repo = g.get_repo('CSSEGISandData/COVID-19')
    contents = repo.get_contents('csse_covid_19_data/csse_covid_19_daily_reports')
    contents = [x.download_url for x in contents if x.name.endswith('.csv')]

    for csv_file in contents:
        stream = codecs.iterdecode(urllib.request.urlopen(csv_file), 'utf-8')
        csv_iter = iter(csv.reader(stream))
        headers = next(csv_iter)
        
        if 'Admin2' not in headers:
            continue

        csv_file_name = os.path.basename(csv_file).split('.csv')[0]
        report_date = datetime.datetime.strptime(csv_file_name, '%m-%d-%Y')
            
        date_headers = [header for header in headers if header.count('-') == 2]
        for row in csv_iter:
            row = dict(zip(headers, row))

            if row['Country_Region'] != 'US':
                continue

            confirmed = int(row['Confirmed'])
            deaths = int(row['Deaths'])
            recovered = int(row['Recovered'])

            country_counts['confirmed'] += confirmed
            country_counts['deaths'] += deaths
            country_counts['recovered'] += recovered

            state = row['Province_State']
            county = row['Admin2']
            
            if state not in states:
                states[state] = AdministrativeDivision.objects.get_or_create(
                    identifier=state,
                    administrative_level=AdministrativeLevel.STATE,
                    parent=country,
                )

            states_counts[state]['confirmed'] += confirmed
            states_counts[state]['deaths'] += deaths
            states_counts[state]['recovered'] += recovered
            
            if county not in counties:
                counties[county] = AdministrativeDivision.objects.get_or_create(
                    identifier=county,
                    administrative_level=AdministrativeLevel.COUNTY,
                    parent=states[state],
                )

            CovidCases.objects.get_or_create(
                division=counties[county],
                date=report_date,
                defaults={
                    'confirmed': confirmed,
                    'deaths': deaths,
                    'recovered': recovered,
                }
            )