import uuid
from django.db import models
from django.conf import settings
from apps.shelters.models import Shelter
from apps.pets.models import Pet


class DonationCampaign(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        COMPLETED = 'completed', 'Completed'
        PAUSED = 'paused', 'Paused'
        CLOSED = 'closed', 'Closed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shelter = models.ForeignKey(Shelter, on_delete=models.CASCADE, related_name='campaigns')
    sponsored_pet = models.ForeignKey(
        Pet, on_delete=models.SET_NULL, null=True, blank=True, related_name='sponsorships'
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    purpose = models.TextField()
    target_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    confirmed_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ACTIVE)
    cover_image = models.URLField(blank=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'donation_campaigns'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class DonationTransaction(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'
        CANCELLED = 'cancelled', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(DonationCampaign, on_delete=models.CASCADE, related_name='transactions')
    donor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    donor_name = models.CharField(max_length=255, blank=True)
    donor_email = models.EmailField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='PHP')
    # NEVER store card details — only provider reference
    provider_reference = models.CharField(max_length=255, blank=True)
    payment_provider = models.CharField(max_length=50, blank=True)  # e.g., 'paymongo'
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    is_anonymous = models.BooleanField(default=False)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'donation_transactions'
        ordering = ['-created_at']
