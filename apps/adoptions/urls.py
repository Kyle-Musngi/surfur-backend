from django.urls import path
from . import views

urlpatterns = [
    path('', views.AdoptionInquiryCreateView.as_view(), name='inquiry_create'),
    path('mine/', views.MyInquiriesView.as_view(), name='my_inquiries'),
    path('<uuid:pk>/', views.InquiryDetailView.as_view(), name='inquiry_detail'),
    path('<uuid:pk>/status/', views.InquiryStatusUpdateView.as_view(), name='inquiry_status_update'),
    path('shelter/<slug:shelter_slug>/', views.ShelterInquiryListView.as_view(), name='shelter_inquiry_list'),
]
