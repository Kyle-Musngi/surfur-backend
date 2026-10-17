from django.contrib import admin
from .models import AdoptionInquiry, InquiryStatusHistory


class InquiryStatusHistoryInline(admin.TabularInline):
    model = InquiryStatusHistory
    extra = 0
    readonly_fields = ('timestamp',)


@admin.register(AdoptionInquiry)
class AdoptionInquiryAdmin(admin.ModelAdmin):
    list_display = ('applicant_name', 'pet', 'shelter', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('applicant_name', 'applicant_email', 'pet__name')
    inlines = [InquiryStatusHistoryInline]
    readonly_fields = ('consent_timestamp',)
