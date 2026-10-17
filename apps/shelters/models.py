import uuid
from django.db import models
from django.conf import settings
from apps.core.models import CebuLocation


class Shelter(models.Model):
    class OrganizationType(models.TextChoices):
        ANIMAL_SHELTER = 'shelter', 'Animal Shelter'
        RESCUE_ORG = 'rescue_org', 'Rescue Organization'
        POUND = 'pound', 'City/Municipal Pound'
        FOSTER_NETWORK = 'foster_network', 'Foster Network'
        OTHER = 'other', 'Other'

    class AnimalType(models.TextChoices):
        DOGS = 'dogs', 'Dogs Only'
        CATS = 'cats', 'Cats Only'
        BOTH = 'both', 'Dogs and Cats'
        OTHER = 'other', 'Other Animals'

    class VerificationStatus(models.TextChoices):
        UNVERIFIED = 'unverified', 'Unverified'
        PENDING = 'pending', 'Pending Review'
        VERIFIED = 'verified', 'Verified'
        REJECTED = 'rejected', 'Rejected'
        SUSPENDED = 'suspended', 'Suspended'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255)
    organization_type = models.CharField(
        max_length=30, choices=OrganizationType.choices,
        default=OrganizationType.ANIMAL_SHELTER
    )
    description = models.TextField(blank=True)
    mission = models.TextField(blank=True)

    # Location
    address = models.TextField()
    city = models.ForeignKey(CebuLocation, on_delete=models.PROTECT, related_name='shelters')
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)

    # Contact
    phone_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)

    # Media
    profile_image = models.TextField(blank=True)
    cover_image = models.TextField(blank=True)

    # Classification
    animal_types = models.CharField(
        max_length=20, choices=AnimalType.choices, default=AnimalType.BOTH
    )

    # Operating hours (stored as JSON: {"monday": "8:00-17:00", ...})
    operating_hours = models.JSONField(default=dict, blank=True)

    # Adoption info
    adoption_requirements = models.TextField(blank=True)

    # Verification
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED
    )
    is_demo = models.BooleanField(default=False, help_text='Demo/seed data — not a real organization')
    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(default=True)

    # Ownership
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='owned_shelters'
    )
    administrators = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='administered_shelters',
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shelters'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def available_pets_count(self):
        return self.pets.filter(adoption_status='available', is_published=True).count()


class ShelterVerification(models.Model):
    class ReviewStatus(models.TextChoices):
        PENDING = 'pending', 'Pending Review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        MORE_INFO = 'more_info', 'More Information Needed'

    shelter = models.ForeignKey(Shelter, on_delete=models.CASCADE, related_name='verification_requests')
    submitted_evidence = models.JSONField(
        default=list, blank=True, help_text='List of uploaded document URLs'
    )
    notes_from_shelter = models.TextField(blank=True)
    review_status = models.CharField(
        max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_verifications'
    )
    review_notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'shelter_verifications'
        ordering = ['-submitted_at']

    def __str__(self):
        return f'Verification for {self.shelter.name} ({self.review_status})'
