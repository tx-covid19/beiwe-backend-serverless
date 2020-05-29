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
    )[0]
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
        csv_file_name = os.path.basename(csv_file).split('.csv')[0]
        report_date = datetime.datetime.strptime(csv_file_name, '%m-%d-%Y')

        if report_date < datetime.datetime.strptime('2020-03-20', '%Y-%m-%d'):
            continue

        stream = codecs.iterdecode(urllib.request.urlopen(csv_file), 'utf-8')
        csv_iter = iter(csv.reader(stream))
        headers = next(csv_iter)
        
        if 'Admin2' not in headers:
            continue

        inserted_data = set([
            d['division']
            for d in CovidCases.objects.filter(date=report_date).values('division').values('division')
        ])

        cases = {}
            
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
                )[0]

            states_counts[state]['confirmed'] += confirmed
            states_counts[state]['deaths'] += deaths
            states_counts[state]['recovered'] += recovered
            
            if (state, county) not in counties:
                counties[(state, county)] = AdministrativeDivision.objects.get_or_create(
                    identifier=county,
                    administrative_level=AdministrativeLevel.COUNTY,
                    parent=states[state],
                )[0]

            if counties[(state, county)].id in inserted_data:
                continue

            cases[(state, county)] = CovidCases(
                division=counties[(state, county)],
                date=report_date,
                confirmed=confirmed,
                deaths=deaths,
                recovered=recovered,
            )
            

        CovidCases.objects.bulk_create(list(cases.values()))

        for state, count in states_counts.items():

            if states[state].id in inserted_data:
                continue

            CovidCases.objects.get_or_create(
                division=states[state],
                date=report_date,
                defaults=count
            )
        
        if country.id in inserted_data:
            continue

        CovidCases.objects.get_or_create(
            division=country,
            date=report_date,
            defaults=country_counts
        )



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