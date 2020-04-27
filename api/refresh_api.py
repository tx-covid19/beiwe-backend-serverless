import functools

from flask import Blueprint, request, jsonify

from database.info_models import save_covid, save_weather, save_pollen
from database.user_models import Researcher
from database.userinfo_models import ParticipantInfo

refresh_api = Blueprint('refresh_api', __name__)


def authenticate_researcher(func):
    @functools.wraps(func)
    def decorated(*args, **kwargs):
        if not request.is_json:
            return jsonify({'msg': 'Missing JSON.'}), 400
        access_key_id = request.json.get('access_key', '')
        access_secret = request.json.get('secret_key', '')

        try:
            researcher = Researcher.objects.get(access_key_id=access_key_id)
        except Researcher.DoesNotExist:
            return jsonify({'msg': 'No access.'}), 403

        if not researcher.validate_access_credentials(access_secret):
            return jsonify({'msg': 'No access.'}), 403

        return func(*args, **kwargs)

    return decorated


def map_save(func):
    info_set = ParticipantInfo.objects.values('country', 'zipcode').distinct()
    count = 0
    for record in info_set:
        country, zipcode = record['country'], record['zipcode']
        if func(country, zipcode):
            count += 1
    return count, len(info_set)


@refresh_api.route('/weather', methods=['POST'])
@authenticate_researcher
def refresh_weather():
    count, total = map_save(save_weather)
    return jsonify({'msg': f'{count}/{total} updated.'}), 200


@refresh_api.route('/pollen', methods=['POST'])
@authenticate_researcher
def refresh_pollen():
    count, total = map_save(save_pollen)
    return jsonify({'msg': f'{count}/{total} updated.'}), 200


# TODO deprecated, need to update the APIs
# @refresh_api.route('/refresh/weather_map', methods=['POST'])
# @authenticate_researcher
# def refresh_weather_map():
#     info_list = list(ParticipantInfo.objects.values('country', 'zipcode').distinct())
#     geo_dict, _ = map_to_county(info_list)
#
#     count = 0
#     try:
#         dt = requests.get('https://static.kinsahealth.com/anomaly_map.json')
#         dt = dt.json()['data']
#         for record in dt:
#             county, state = record[1], record[2]
#             if (county, state) in geo_dict:
#                 for country, zipcode in geo_dict[(county, state)]:
#                     HealthWeather(last_updated=timezone.now(), country=country, zipcode=zipcode,
#                                   observed_illness=record[3],
#                                   severity_last_week='', severity_this_week='',
#                                   severity_next_week='').save()
#                     count += 1
#     except:
#         raise
#     return jsonify({'msg': f'{count}/{len(info_list)} updated.'}), 200


@refresh_api.route('/covid', methods=['POST'])
@authenticate_researcher
def refresh_covid():
    info_list = list(ParticipantInfo.objects.values('country', 'zipcode').distinct())
    save_covid(info_list)
    return jsonify({'msg': 'updated.'}), 200
