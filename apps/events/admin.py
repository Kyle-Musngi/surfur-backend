from django.contrib import admin
from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'host_shelter', 'event_type', 'start_datetime', 'status', 'is_published')
    list_filter = ('event_type', 'status', 'is_published')
    search_fields = ('title', 'host_shelter__name')
