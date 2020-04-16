from rest_framework import serializers
from ..info_models import CovidCase, Weather, Pollen


class CovidCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = CovidCase
        fields = '__all__'


class WeatherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Weather
        fields = '__all__'


class PollenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pollen
        fields = '__all__'
