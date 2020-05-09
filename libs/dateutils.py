from datetime import datetime
import pytz

from config.constants import API_TIME_FORMAT
from config.settings import TIMEZONE

def str_to_datetime(time_string):
    """ Translates a time string to a datetime object, raises a 400 if the format is wrong."""

    local_timezone = pytz.timezone(TIMEZONE)
    try:
        return local_timezone.localize(datetime.strptime(time_string, API_TIME_FORMAT))
    except ValueError as e:
        if "does not match format" in str(e):
            return abort(400)

