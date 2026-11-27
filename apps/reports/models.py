import uuid
import random
import string
from django.db import models
from django.conf import settings
from apps.core.models import CebuLocation
from apps.shelters.models import Shelter


class StrayReport(models.Model):
    class AnimalType(models.TextChoices):
        DOG = 'dog', 'Dog'
        CAT = 'cat', 'Cat'
        OTHER = 'other', 'Other'
        UNKNOWN = 'unknown', 'Unknown'

    class Urgency(models.TextChoices):
        CRITICAL = 'critical', 'Critical - Injured/Life-Threatening'
        HIGH = 'high', 'High - Needs Prompt Attention'
        MEDIUM = 'medium', 'Medium - Stray, Appears Healthy'
        LOW = 'low', 'Low - Observation Only'

    class Status(models.TextChoices):
        SUBMITTED = 'submitted', 'Submitted'
        UNDER_REVIEW = 'under_review', 'Under Review'
        ASSIGNED = 'assigned', 'Assigned to Rescue Team / Shelter'
        RESCUE_IN_PROGRESS = 'rescue_in_progress', 'Rescue in Progress'
        RESCUED = 'rescued', 'Successfully Rescued'
        RESOLVED = 'resolved', 'Resolved'
        UNABLE_TO_LOCATE = 'unable_to_locate', 'Unable to Locate'
        DUPLICATE = 'duplicate', 'Duplicate Report'
        REJECTED = 'rejected', 'Rejected / Invalid Report'
        CANCELLED = 'cancelled', 'Cancelled'
        # Legacy statuses kept for backward compatibility
        REFERRED = 'referred', 'Referred to Rescue Group'
        ASSISTANCE_ARRANGED = 'assistance_arranged', 'Assistance Arranged'
        UNABLE_TO_VERIFY = 'unable_to_verify', 'Unable to Verify'

    class ReporterType(models.TextChoices):
        REGISTERED = 'registered', 'Registered User'
        GUEST = 'guest', 'Guest Reporter'

    class PreferredContact(models.TextChoices):
        PHONE = 'phone', 'Mobile Phone'
        EMAIL = 'email', 'Email Address'
        ANY = 'any', 'Either Phone or Email'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_number = models.CharField(max_length=20, unique=True)
    reporter_type = models.CharField(
        max_length=20, choices=ReporterType.choices, default=ReporterType.GUEST
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='stray_reports'
    )
    reporter_name = models.CharField(max_length=255, blank=True)
    reporter_email = models.EmailField(blank=True)
    reporter_phone = models.CharField(max_length=20, blank=True)
    preferred_contact_method = models.CharField(
        max_length=10, choices=PreferredContact.choices, default=PreferredContact.PHONE
    )
    contact_verified = models.BooleanField(default=False)
    contact_verification_token_hash = models.CharField(max_length=128, blank=True)
    contact_verification_expires_at = models.DateTimeField(null=True, blank=True)
    tracking_token_hash = models.CharField(max_length=128, blank=True)

    animal_type = models.CharField(
        max_length=10, choices=AnimalType.choices, default=AnimalType.UNKNOWN
    )
    estimated_animal_count = models.PositiveSmallIntegerField(default=1)
    animal_description = models.TextField()
    animal_condition = models.TextField(blank=True)
    photo = models.ImageField(upload_to='stray_reports/', null=True, blank=True)
    image_urls = models.JSONField(default=list, blank=True)

    # Location (protected — not fully public)
    city = models.ForeignKey(CebuLocation, on_delete=models.SET_NULL, null=True, blank=True)
    barangay = models.CharField(max_length=120, blank=True)
    location_description = models.TextField(
        blank=True, help_text='Landmark or approximate location description'
    )
    additional_location_instructions = models.TextField(blank=True)
    # Coordinates stored but NOT exposed publicly
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    sighted_at = models.DateTimeField()
    urgency = models.CharField(max_length=10, choices=Urgency.choices, default=Urgency.MEDIUM)

    status = models.CharField(max_length=25, choices=Status.choices, default=Status.SUBMITTED)
    is_potential_duplicate = models.BooleanField(default=False)
    duplicate_flag_reason = models.CharField(max_length=255, blank=True)
    assigned_organization = models.ForeignKey(
        Shelter,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_reports'
    )
    resolution_notes = models.TextField(blank=True)
    data_processing_consent = models.BooleanField(default=False)

    rescued_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stray_reports'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.report_number:
            import datetime
            year = datetime.date.today().year
            suffix = ''.join(random.choices(string.digits, k=6))
            self.report_number = f'SF-{year}-{suffix}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Report {self.report_number} - {self.animal_type} in {self.city}'


class StrayReportStatusHistory(models.Model):
    report = models.ForeignKey(StrayReport, on_delete=models.CASCADE, related_name='status_history')
    old_status = models.CharField(max_length=25, blank=True)
    new_status = models.CharField(max_length=25)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    assigned_organization = models.ForeignKey(
        Shelter,
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    public_note = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stray_report_status_history'
        ordering = ['timestamp']

    def __str__(self):
        return f'{self.report.report_number}: {self.old_status} -> {self.new_status}'
