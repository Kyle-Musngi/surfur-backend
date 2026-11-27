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


class ImageCapabilitiesView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from .images import IMAGE_EXTENSIONS, MAX_PIXELS, MAX_SIDE
        return Response({
            'normalization': 'raster-v1',
            'extensions': sorted(IMAGE_EXTENSIONS),
            'max_upload_mb': 5, 'max_pixels': MAX_PIXELS, 'max_side': MAX_SIDE,
            'output_formats': ['image/jpeg', 'image/png'],
            'animation': 'first_frame',
        })


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
