from django.urls import path
from . import views

urlpatterns = [
    path('image-capabilities/', views.ImageCapabilitiesView.as_view(), name='image_capabilities'),
    path('locations/', views.LocationListView.as_view(), name='location_list'),
    path('config/', views.PlatformConfigView.as_view(), name='platform_config'),
]
