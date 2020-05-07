from rest_framework import serializers

from ..event_models import Event


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        exclude = ['id', 'date', 'user']
