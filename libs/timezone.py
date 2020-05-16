from datetime import datetime
from pytz import timezone
from pytz import utc


def now():
    return datetime.utcnow().replace(tzinfo=utc)


def to_utc(d, tz):
    tz = timezone(tz)
    return tz.normalize(tz.localize(d)).astimezone(utc)


def to_local(d, tz):
    tz = timezone(tz)
    return d.replace(tzinfo=utc).astimezone(tz)
