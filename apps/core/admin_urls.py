from django.urls import path
from . import admin_views

urlpatterns = [
    path('dashboard/', admin_views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('shelters/', admin_views.AdminShelterListCreateView.as_view(), name='admin_shelters'),
    path('shelters/<uuid:pk>/', admin_views.AdminShelterDetailUpdateView.as_view(), name='admin_shelter_detail'),
    path('shelters/<uuid:pk>/action/', admin_views.AdminShelterActionView.as_view(), name='admin_shelter_action'),
    path('shelters/<uuid:pk>/administrators/', admin_views.AdminShelterAdministratorsView.as_view(), name='admin_shelter_admins'),
    path('shelters/<uuid:pk>/administrators/<uuid:user_id>/', admin_views.AdminShelterAdministratorRemoveView.as_view(), name='admin_shelter_admin_remove'),
    path('users/', admin_views.AdminUserListView.as_view(), name='admin_users'),
    path('users/<uuid:pk>/', admin_views.AdminUserUpdateView.as_view(), name='admin_user_update'),
    path('users/<uuid:pk>/reset-password/', admin_views.AdminUserPasswordResetView.as_view(), name='admin_user_reset_password'),
    path('animals/', admin_views.AdminAnimalListCreateView.as_view(), name='admin_animals'),
    path('animals/<uuid:pk>/', admin_views.AdminAnimalDetailUpdateView.as_view(), name='admin_animal_detail'),
    path('adoptions/', admin_views.AdminAdoptionMonitoringListView.as_view(), name='admin_adoptions'),
    path('stray-reports/', admin_views.AdminStrayReportListView.as_view(), name='admin_stray_reports'),
    path('stray-reports/<uuid:pk>/', admin_views.AdminStrayReportUpdateView.as_view(), name='admin_stray_report_update'),
    path('reports/', admin_views.AdminReportsView.as_view(), name='admin_reports'),
    path('reports/export/', admin_views.AdminReportsExportCSVView.as_view(), name='admin_reports_export'),
    path('audit-logs/', admin_views.AdminAuditLogListView.as_view(), name='admin_audit_logs'),
    path('audit-logs/export/', admin_views.AdminAuditLogExportCSVView.as_view(), name='admin_audit_logs_export'),
    path('settings/', admin_views.AdminPlatformSettingsView.as_view(), name='admin_settings'),
]

