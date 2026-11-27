from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import CebuLocation, PlatformSetting
from .serializers import CebuLocationSerializer
from django.conf import settings


class LocationListView(generics.ListAPIView):
    queryset = CebuLocation.objects.filter(is_active=True).order_by('name')
    serializer_class = CebuLocationSerializer
    permission_classes = [permissions.AllowAny]


class PlatformConfigView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        platform_settings = PlatformSetting.get_solo()
        return Response({
            'service_area': {
                'province': settings.SERVICE_AREA_PROVINCE,
                'country': settings.SERVICE_AREA_COUNTRY,
            },
            'maps_configured': bool(settings.GOOGLE_MAPS_API_KEY),
            'cloudinary_configured': bool(settings.CLOUDINARY_CLOUD_NAME),
            'payments_configured': False,
            'contact_email': platform_settings.contact_email,
            'contact_phone': platform_settings.contact_phone,
            'support_desk_name': platform_settings.support_desk_name,
            'shelter_onboarding_message': platform_settings.shelter_onboarding_message,
        })
