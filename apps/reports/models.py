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
        REFERRED = 'referred', 'Referred to Rescue Group'
        ASSISTANCE_ARRANGED = 'assistance_arranged', 'Assistance Arranged'
        RESOLVED = 'resolved', 'Resolved'
        UNABLE_TO_VERIFY = 'unable_to_verify', 'Unable to Verify'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_number = models.CharField(max_length=20, unique=True)
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='stray_reports'
    )
    reporter_name = models.CharField(max_length=255, blank=True)
    reporter_email = models.EmailField(blank=True)
    reporter_phone = models.CharField(max_length=20, blank=True)

    animal_type = models.CharField(
        max_length=10, choices=AnimalType.choices, default=AnimalType.UNKNOWN
    )
    animal_description = models.TextField()
    animal_condition = models.TextField(blank=True)
    image_urls = models.JSONField(default=list, blank=True)

    # Location (protected — not fully public)
    city = models.ForeignKey(CebuLocation, on_delete=models.SET_NULL, null=True, blank=True)
    location_description = models.TextField(
        blank=True, help_text='Landmark or approximate location description'
    )
    # Coordinates stored but NOT exposed publicly
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    sighted_at = models.DateTimeField()
    urgency = models.CharField(max_length=10, choices=Urgency.choices, default=Urgency.MEDIUM)

    status = models.CharField(max_length=25, choices=Status.choices, default=Status.SUBMITTED)
    assigned_organization = models.ForeignKey(
        Shelter,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_reports'
    )
    resolution_notes = models.TextField(blank=True)
    data_processing_consent = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stray_reports'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.report_number:
            self.report_number = 'RPT-' + ''.join(
                random.choices(string.ascii_uppercase + string.digits, k=8)
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Report {self.report_number} - {self.animal_type} in {self.city}'
