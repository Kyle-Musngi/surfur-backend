import mimetypes
from pathlib import Path
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.http import FileResponse, Http404
from django.utils._os import safe_join
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


def serve_public_media(request, path):
    """Serve uploaded public media from MEDIA_ROOT in all environments (including DEBUG=False)."""
    media_root = Path(settings.MEDIA_ROOT).resolve()
    try:
        full_path = Path(safe_join(str(media_root), path)).resolve()
    except Exception:
        raise Http404('Media file not found.')
    if not full_path.is_file() or (media_root not in full_path.parents):
        raise Http404('Media file not found.')
    content_type, _ = mimetypes.guess_type(str(full_path))
    response = FileResponse(open(full_path, 'rb'), content_type=content_type or 'application/octet-stream')
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cross-Origin-Resource-Policy'] = 'cross-origin'
    response['Cache-Control'] = 'public, max-age=86400'
    return response

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
    path('api/v1/admin-panel/', include('apps.core.admin_urls')),
    path('api/v1/shelters/', include('apps.shelters.urls')),
    path('api/v1/pets/', include('apps.pets.urls')),
    path('api/v1/adoptions/', include('apps.adoptions.urls')),
    path('api/v1/reports/', include('apps.reports.urls')),
    path('api/v1/events/', include('apps.events.urls')),
    path('api/v1/donations/', include('apps.donations.urls')),
    path('api/v1/articles/', include('apps.articles.urls')),
    path('api/v1/notifications/', include('apps.notifications.urls')),
    path('api/v1/messaging/', include('apps.messaging.urls')),
    # API Schema
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    # Public uploaded media (pets, stray_reports, etc.) — private_media/ is never under MEDIA_ROOT
    re_path(r'^media/(?P<path>.*)$', serve_public_media, name='public_media'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
