from django.urls import path
from . import views

urlpatterns = [
    path('', views.ShelterListView.as_view(), name='shelter_list'),
    path('register/', views.ShelterRegisterView.as_view(), name='shelter_register'),
    path('<slug:slug>/', views.ShelterDetailView.as_view(), name='shelter_detail'),
]
