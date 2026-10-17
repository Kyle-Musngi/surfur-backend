from django.contrib import admin
from .models import DonationCampaign, DonationTransaction


class DonationTransactionInline(admin.TabularInline):
    model = DonationTransaction
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(DonationCampaign)
class DonationCampaignAdmin(admin.ModelAdmin):
    list_display = ('title', 'shelter', 'status', 'confirmed_amount', 'target_amount', 'is_published')
    list_filter = ('status', 'is_published')
    search_fields = ('title', 'shelter__name')
    inlines = [DonationTransactionInline]


@admin.register(DonationTransaction)
class DonationTransactionAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'donor_name', 'amount', 'currency', 'status', 'created_at')
    list_filter = ('status', 'currency')
    readonly_fields = ('provider_reference',)
