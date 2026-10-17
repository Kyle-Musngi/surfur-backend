from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

@api_view(['GET'])
@permission_classes([AllowAny])
def api_root(request):
    return Response({
        'name': 'SurFur REST API',
        'tagline': 'Surf for Paws, Find Your Furever Home — Philippines',
        'version': '1.0.0',
        'documentation': '/api/docs/',
        'admin_panel': '/admin/',
        'frontend_url': 'http://localhost:5173',
        'endpoints': {
            'auth': '/api/v1/auth/',
            'pets': '/api/v1/pets/',
            'shelters': '/api/v1/shelters/',
            'adoptions': '/api/v1/adoptions/',
            'reports': '/api/v1/reports/',
            'events': '/api/v1/events/',
            'donations': '/api/v1/donations/',
            'articles': '/api/v1/articles/',
            'notifications': '/api/v1/notifications/',
            'cebu_locations': '/api/v1/core/locations/',
        }
    })

urlpatterns = [
    path('', api_root, name='api_root'),
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('apps.accounts.urls')),
    path('api/v1/core/', include('apps.core.urls')),
    path('api/v1/shelters/', include('apps.shelters.urls')),
    path('api/v1/pets/', include('apps.pets.urls')),
    path('api/v1/adoptions/', include('apps.adoptions.urls')),
    path('api/v1/reports/', include('apps.reports.urls')),
    path('api/v1/events/', include('apps.events.urls')),
    path('api/v1/donations/', include('apps.donations.urls')),
    path('api/v1/articles/', include('apps.articles.urls')),
    path('api/v1/notifications/', include('apps.notifications.urls')),
    # API Schema
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
