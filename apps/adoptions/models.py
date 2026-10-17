import uuid
import datetime
import random
import string
from django.db import models
from django.conf import settings
from apps.pets.models import Pet
from apps.shelters.models import Shelter


class AdoptionInquiry(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = 'submitted', 'Submitted'
        UNDER_REVIEW = 'under_review', 'Under Review'
        MORE_INFO = 'more_info', 'Additional Information Required'
        VISIT_REQUESTED = 'visit_requested', 'Visit Requested'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        DECLINED = 'declined', 'Declined'
        WITHDRAWN = 'withdrawn', 'Withdrawn'
        COMPLETED = 'completed', 'Completed'

    class ContactPreference(models.TextChoices):
        EMAIL = 'email', 'Email'
        PHONE = 'phone', 'Phone'
        MESSENGER = 'messenger', 'Facebook Messenger'

    class LivingSituation(models.TextChoices):
        HOUSE_WITH_YARD = 'house_yard', 'House with yard'
        HOUSE_NO_YARD = 'house_no_yard', 'House without yard'
        APARTMENT = 'apartment', 'Apartment/Condo'
        BOARDING = 'boarding', 'Boarding house'
        OTHER = 'other', 'Other'

    class HousingType(models.TextChoices):
        HOMEOWNER = 'homeowner', 'Homeowner'
        RENTER = 'renter', 'Renter'
        OTHER = 'other', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference_number = models.CharField(max_length=32, unique=True, blank=True, db_index=True)

    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adoption_inquiries'
    )
    pet = models.ForeignKey(Pet, on_delete=models.CASCADE, related_name='inquiries')
    shelter = models.ForeignKey(Shelter, on_delete=models.CASCADE, related_name='inquiries')

    # Applicant info
    applicant_name = models.CharField(max_length=255)
    applicant_email = models.EmailField()
    applicant_phone = models.CharField(max_length=20, blank=True)
    applicant_city = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    occupation = models.CharField(max_length=150, blank=True)
    contact_preference = models.CharField(
        max_length=20, choices=ContactPreference.choices, default=ContactPreference.EMAIL
    )

    # Housing & Living Setup
    housing_type = models.CharField(
        max_length=20, choices=HousingType.choices, default=HousingType.HOMEOWNER
    )
    living_situation = models.CharField(max_length=20, choices=LivingSituation.choices, blank=True)
    
    # Document Verification Uploads
    proof_of_id = models.FileField(upload_to='adoptions/ids/', blank=True, null=True)
    proof_of_address = models.FileField(upload_to='adoptions/address/', blank=True, null=True)
    proof_of_income = models.FileField(upload_to='adoptions/income/', blank=True, null=True)
    proof_of_housing = models.FileField(
        upload_to='adoptions/housing/', blank=True, null=True,
        help_text='Homeownership title or Landlord consent agreement'
    )
    home_environment_media = models.FileField(
        upload_to='adoptions/home_env/', blank=True, null=True,
        help_text='Photo or video walkthrough of home and pet areas'
    )

    # Experience & Vet references
    has_existing_pets = models.BooleanField(null=True, blank=True)
    existing_pets_description = models.TextField(blank=True)
    has_owned_pets_before = models.BooleanField(default=False)
    vet_reference_name = models.CharField(max_length=200, blank=True)
    vet_reference_contact = models.CharField(max_length=100, blank=True)

    # Household & Care commitment
    has_children = models.BooleanField(null=True, blank=True)
    pet_care_experience = models.TextField(blank=True)
    reason_for_adopting = models.TextField(blank=True)
    long_term_care_acknowledgment = models.BooleanField(default=False)

    # Consent
    data_processing_consent = models.BooleanField(default=False)
    responsible_adoption_agreement = models.BooleanField(default=False)
    consent_timestamp = models.DateTimeField(null=True, blank=True)

    # Status tracking & Shelter Review
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_inquiries'
    )
    shelter_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'adoption_inquiries'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.reference_number:
            date_str = datetime.date.today().strftime('%Y%m%d')
            random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
            self.reference_number = f'APP-{date_str}-{random_suffix}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.reference_number} - {self.applicant_name} for {self.pet.name}'


class InquiryStatusHistory(models.Model):
    inquiry = models.ForeignKey(AdoptionInquiry, on_delete=models.CASCADE, related_name='status_history')
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True
    )
    notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inquiry_status_history'
        ordering = ['timestamp']
