from django.urls import path
from . import views

urlpatterns = [
    path('', views.CampaignListView.as_view(), name='campaign_list'),
    path('<uuid:pk>/', views.CampaignDetailView.as_view(), name='campaign_detail'),
]
