from django.urls import path
from . import views

urlpatterns = [
    path('', views.ShelterListView.as_view(), name='shelter_list'),
    path('my-shelter/', views.MyShelterView.as_view(), name='my_shelter'),
    path('my-shelter/stats/', views.MyShelterStatsView.as_view(), name='my_shelter_stats'),
    path('register/', views.ShelterRegisterView.as_view(), name='shelter_register'),
    path('<slug:slug>/', views.ShelterDetailView.as_view(), name='shelter_detail'),
]
