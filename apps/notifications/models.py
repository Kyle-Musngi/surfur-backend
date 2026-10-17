import uuid
from django.db import models
from django.conf import settings


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        INQUIRY_UPDATE = 'inquiry_update', 'Adoption Inquiry Update'
        FAVORITE_UPDATE = 'favorite_update', 'Favorited Pet Update'
        NEW_PET = 'new_pet', 'New Pet Match'
        EVENT_REMINDER = 'event_reminder', 'Event Reminder'
        SHELTER_MESSAGE = 'shelter_message', 'Message from Shelter'
        SYSTEM = 'system', 'System Notification'
        VERIFICATION = 'verification', 'Verification Update'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications'
    )
    notification_type = models.CharField(max_length=30, choices=NotificationType.choices)
    title = models.CharField(max_length=255)
    message = models.TextField()
    related_resource_type = models.CharField(max_length=50, blank=True)  # 'pet', 'inquiry', etc.
    related_resource_id = models.CharField(max_length=100, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.notification_type} for {self.user.email}'
