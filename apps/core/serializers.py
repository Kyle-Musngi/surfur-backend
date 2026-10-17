from rest_framework import serializers
from .models import CebuLocation


class CebuLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CebuLocation
        fields = ('id', 'name', 'location_type', 'province', 'latitude', 'longitude')
