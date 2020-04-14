from datetime import datetime

from rest_framework import serializers

from database.tracker_models import TrackRecord


class DateTimeFieldWithTZ(serializers.DateTimeField):
    def to_representation(self, value: datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')


class TrackerRecordSerializer(serializers.ModelSerializer):
    track_date = DateTimeFieldWithTZ()

    class Meta:
        model = TrackRecord
        exclude = ['user', 'last_update']
