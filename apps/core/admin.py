from django.contrib import admin
from .models import CebuLocation, AuditLog


@admin.register(CebuLocation)
class CebuLocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'location_type', 'province', 'is_active')
    list_filter = ('location_type', 'is_active')
    search_fields = ('name',)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('actor_email', 'action', 'resource_type', 'timestamp')
    list_filter = ('action',)
    readonly_fields = ('timestamp',)
