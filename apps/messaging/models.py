import os
import uuid
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils import timezone
from apps.pets.models import Pet
from apps.shelters.models import Shelter

private_messaging_storage = FileSystemStorage(
    location=settings.BASE_DIR / 'private_media'
)


def unread_after(read_state):
    condition = models.Q(created_at__gt=read_state.last_read_at)
    if read_state.last_read_message_id:
        condition |= models.Q(created_at=read_state.last_read_at, id__gt=read_state.last_read_message_id)
    return condition


def get_private_messaging_storage():
    return private_messaging_storage


def messaging_attachment_path(instance, filename):
    ext = os.path.splitext(filename or '')[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.pdf'):
        ext = '.bin'
    return f"messaging/{instance.message.conversation_id}/{uuid.uuid4().hex}{ext}"


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shelter = models.OneToOneField(
        Shelter,
        on_delete=models.CASCADE,
        related_name='conversation',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = 'messaging_conversations'
        ordering = ['-last_activity_at']

    def __str__(self):
        return f"Conversation({self.shelter.name})"


class Message(models.Model):
    class RequestType(models.TextChoices):
        GENERAL = 'general', 'General Inquiry'
        ADD_ANIMAL = 'add_animal', 'Request to Add an Animal'
        UPDATE_ANIMAL = 'update_animal', 'Request Animal Information Update'
        UPDATE_SHELTER = 'update_shelter', 'Request Shelter Information Update'
        UPDATE_PHOTO = 'update_photo', 'Request Photograph Update'
        REMOVE_ANIMAL = 'remove_animal', 'Request Animal Listing Removal'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_shelter_messages',
    )
    content = models.TextField(blank=True)
    request_type = models.CharField(
        max_length=32,
        choices=RequestType.choices,
        default=RequestType.GENERAL,
    )
    related_pet = models.ForeignKey(
        Pet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='messaging_references',
    )
    request_metadata = models.JSONField(default=dict, blank=True)
    client_id = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'messaging_messages'
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['conversation', 'sender', 'client_id'],
                condition=~models.Q(client_id=''),
                name='messaging_unique_client_submission',
            ),
        ]

    def __str__(self):
        return f"Message({self.id}, {self.request_type})"


class MessageAttachment(models.Model):
    class FileType(models.TextChoices):
        IMAGE = 'image', 'Image'
        PDF = 'pdf', 'PDF Document'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='attachments',
    )
    file = models.FileField(
        upload_to=messaging_attachment_path,
        storage=get_private_messaging_storage,
    )
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=16, choices=FileType.choices)
    mime_type = models.CharField(max_length=100)
    file_size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'messaging_attachments'
        ordering = ['created_at']


class MessageReadState(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='read_states',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='messaging_read_states',
    )
    last_read_message = models.ForeignKey(
        Message,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    last_read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'messaging_read_states'
        unique_together = ('conversation', 'user')
