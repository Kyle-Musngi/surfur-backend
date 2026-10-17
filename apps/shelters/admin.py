from django.contrib import admin
from .models import Shelter, ShelterVerification


@admin.register(Shelter)
class ShelterAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'organization_type', 'verification_status', 'is_demo', 'is_active')
    list_filter = ('verification_status', 'organization_type', 'animal_types', 'is_demo')
    search_fields = ('name', 'email')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(ShelterVerification)
class ShelterVerificationAdmin(admin.ModelAdmin):
    list_display = ('shelter', 'review_status', 'submitted_at', 'reviewed_at')
    list_filter = ('review_status',)
