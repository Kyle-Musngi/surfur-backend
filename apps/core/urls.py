from django.urls import path
from . import views

urlpatterns = [
    path('locations/', views.LocationListView.as_view(), name='location_list'),
    path('config/', views.PlatformConfigView.as_view(), name='platform_config'),
]
