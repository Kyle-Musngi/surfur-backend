import uuid
from django.db import models
from apps.shelters.models import Shelter
from apps.core.models import CebuLocation


class Event(models.Model):
    class EventType(models.TextChoices):
        ADOPTION_DRIVE = 'adoption_drive', 'Adoption Drive'
        EDUCATION = 'education', 'Pet Education Session'
        VOLUNTEER = 'volunteer', 'Volunteer Activity'
        FUNDRAISING = 'fundraising', 'Fundraising Event'
        OPEN_DAY = 'open_day', 'Shelter Open Day'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        UPCOMING = 'upcoming', 'Upcoming'
        ONGOING = 'ongoing', 'Ongoing'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host_shelter = models.ForeignKey(Shelter, on_delete=models.CASCADE, related_name='events')
    title = models.CharField(max_length=255)
    description = models.TextField()
    event_type = models.CharField(
        max_length=20, choices=EventType.choices, default=EventType.ADOPTION_DRIVE
    )

    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField(null=True, blank=True)
    timezone = models.CharField(max_length=50, default='Asia/Manila')

    venue_name = models.CharField(max_length=255, blank=True)
    venue_address = models.TextField(blank=True)
    city = models.ForeignKey(CebuLocation, on_delete=models.SET_NULL, null=True, blank=True)
    maps_link = models.URLField(blank=True)

    contact_info = models.TextField(blank=True)
    registration_required = models.BooleanField(default=False)
    registration_link = models.URLField(blank=True)
    cover_photo = models.URLField(blank=True)

    status = models.CharField(max_length=15, choices=Status.choices, default=Status.UPCOMING)
    is_published = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'events'
        ordering = ['start_datetime']

    def __str__(self):
        return f'{self.title} by {self.host_shelter.name}'
