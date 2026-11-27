from django.urls import path
from . import views

urlpatterns = [
    path('', views.StrayReportCreateView.as_view(), name='report_create'),
    path('track/', views.GuestTrackReportView.as_view(), name='report_track'),
    path('verify-contact/', views.GuestVerifyContactView.as_view(), name='report_verify_contact'),
    path('claim/', views.ClaimGuestReportView.as_view(), name='report_claim'),
    path('mine/', views.MyReportsView.as_view(), name='my_reports'),
    path('mine/<uuid:pk>/', views.MyReportDetailView.as_view(), name='my_report_detail'),
    path('shelter-assigned/', views.ShelterAssignedReportListView.as_view(), name='shelter_assigned_reports'),
    path('shelter-assigned/<uuid:pk>/', views.ShelterAssignedReportUpdateView.as_view(), name='shelter_assigned_report_update'),
]
