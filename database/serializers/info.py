from rest_framework import serializers
from ..info_models import CovidCase


class CovidCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = CovidCase
        exclude = ['counties_json']
