import uuid
from django.db import models
from django.conf import settings
from apps.shelters.models import Shelter
from apps.core.models import CebuLocation


class Pet(models.Model):
    class Species(models.TextChoices):
        DOG = 'dog', 'Dog'
        CAT = 'cat', 'Cat'
        OTHER = 'other', 'Other'

    class Sex(models.TextChoices):
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'
        UNKNOWN = 'unknown', 'Unknown'

    class Size(models.TextChoices):
        SMALL = 'small', 'Small'
        MEDIUM = 'medium', 'Medium'
        LARGE = 'large', 'Large'
        UNKNOWN = 'unknown', 'Unknown'

    class AdoptionStatus(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        PENDING = 'pending', 'Adoption Pending'
        ADOPTED = 'adopted', 'Adopted'
        HOLD = 'hold', 'On Hold'
        UNAVAILABLE = 'unavailable', 'Unavailable'

    class AgeCategory(models.TextChoices):
        BABY = 'baby', 'Baby/Puppy/Kitten'
        YOUNG = 'young', 'Young'
        ADULT = 'adult', 'Adult'
        SENIOR = 'senior', 'Senior'
        UNKNOWN = 'unknown', 'Unknown'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shelter = models.ForeignKey(Shelter, on_delete=models.CASCADE, related_name='pets')
    name = models.CharField(max_length=100)
    species = models.CharField(max_length=10, choices=Species.choices)
    breed = models.CharField(max_length=100, blank=True)
    sex = models.CharField(max_length=10, choices=Sex.choices, default=Sex.UNKNOWN)

    # Age
    estimated_birth_date = models.DateField(null=True, blank=True)
    age_years = models.PositiveSmallIntegerField(null=True, blank=True)
    age_months = models.PositiveSmallIntegerField(null=True, blank=True)
    age_category = models.CharField(max_length=10, choices=AgeCategory.choices, default=AgeCategory.UNKNOWN)

    size = models.CharField(max_length=10, choices=Size.choices, default=Size.UNKNOWN)
    color = models.CharField(max_length=100, blank=True)

    description = models.TextField(blank=True)
    personality = models.TextField(blank=True)
    rescue_story = models.TextField(blank=True)

    # Health
    is_vaccinated = models.BooleanField(null=True, blank=True)
    is_dewormed = models.BooleanField(null=True, blank=True)
    is_sterilized = models.BooleanField(null=True, blank=True)
    has_special_needs = models.BooleanField(default=False)
    special_needs_description = models.TextField(blank=True)
    health_notes = models.TextField(blank=True)

    # Compatibility (null = not assessed)
    good_with_children = models.BooleanField(null=True, blank=True)
    good_with_dogs = models.BooleanField(null=True, blank=True)
    good_with_cats = models.BooleanField(null=True, blank=True)

    # Status
    adoption_status = models.CharField(
        max_length=15,
        choices=AdoptionStatus.choices,
        default=AdoptionStatus.AVAILABLE
    )
    is_published = models.BooleanField(default=False)

    # Location (inherits shelter city but stored for query convenience)
    city = models.ForeignKey(
        CebuLocation,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='pets'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pets'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['species', 'adoption_status', 'is_published']),
            models.Index(fields=['shelter', 'adoption_status']),
            models.Index(fields=['age_category', 'size', 'sex']),
        ]

    def __str__(self):
        return f'{self.name} ({self.species}) - {self.shelter.name}'

    def save(self, *args, **kwargs):
        # Auto-set city from shelter if not set
        if not self.city_id and self.shelter_id:
            self.city = self.shelter.city
        super().save(*args, **kwargs)


class PetImage(models.Model):
    pet = models.ForeignKey(Pet, on_delete=models.CASCADE, related_name='images')
    image_url = models.URLField()
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    display_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'pet_images'
        ordering = ['display_order', 'created_at']

    def save(self, *args, **kwargs):
        if self.is_primary:
            PetImage.objects.filter(pet=self.pet, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class Favorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorites'
    )
    pet = models.ForeignKey(Pet, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'favorites'
        unique_together = [('user', 'pet')]
        ordering = ['-created_at']
