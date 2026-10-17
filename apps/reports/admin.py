from django.contrib import admin
from .models import StrayReport


@admin.register(StrayReport)
class StrayReportAdmin(admin.ModelAdmin):
    list_display = ('report_number', 'animal_type', 'city', 'urgency', 'status', 'created_at')
    list_filter = ('status', 'urgency', 'animal_type')
    search_fields = ('report_number', 'reporter_name', 'reporter_email')
    readonly_fields = ('report_number', 'created_at', 'updated_at')
