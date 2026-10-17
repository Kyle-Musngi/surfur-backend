from django.urls import path
from . import views

urlpatterns = [
    path('', views.StrayReportCreateView.as_view(), name='report_create'),
    path('mine/', views.MyReportsView.as_view(), name='my_reports'),
]
