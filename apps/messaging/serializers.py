import os
from pypdf import PdfReader
from pypdf.generic import IndirectObject, DictionaryObject, ArrayObject
from rest_framework import serializers
from apps.core.validators import resolve_media_url
from apps.core.images import IMAGE_EXTENSIONS, normalize_image
from .models import Conversation, Message, MessageAttachment, MessageReadState, unread_after

MAX_ATTACHMENTS_PER_MESSAGE = 5
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 20 * 1024 * 1024

ALLOWED_IMAGE_EXTS = IMAGE_EXTENSIONS
ALLOWED_PDF_EXTS = {'.pdf'}


def validate_pdf(file):
    """Accept passive, structurally valid PDFs; reject actions and embedded content."""
    reader = PdfReader(file, strict=True)
    if reader.is_encrypted or not 0 < len(reader.pages) <= 200:
        raise ValueError('Encrypted or oversized PDF')
    pending, seen = [reader.trailer], set()
    blocked = {'/A', '/AA', '/OpenAction', '/JS', '/JavaScript', '/EmbeddedFiles',
               '/EF', '/XFA', '/RichMediaContent', '/Launch', '/AcroForm'}
    for _ in range(20000):
        if not pending:
            return
        obj = pending.pop()
        if isinstance(obj, IndirectObject):
            key = (obj.idnum, obj.generation)
            if key in seen:
                continue
            seen.add(key)
            obj = obj.get_object()
        if isinstance(obj, DictionaryObject):
            if blocked.intersection(obj.keys()):
                raise ValueError('Active PDF content')
            pending.extend(obj.values())
        elif isinstance(obj, ArrayObject):
            pending.extend(obj)
    raise ValueError('PDF is too complex')


def validate_messaging_attachments(files):
    if len(files) > MAX_ATTACHMENTS_PER_MESSAGE:
        raise serializers.ValidationError(
            f'Maximum {MAX_ATTACHMENTS_PER_MESSAGE} attachments allowed per message.'
        )
    total_size = 0
    validated = []
    for f in files:
        size = getattr(f, 'size', 0) or 0
        total_size += size
        if total_size > MAX_TOTAL_ATTACHMENT_BYTES:
            raise serializers.ValidationError(
                'Total attachment size per message cannot exceed 20 MB.'
            )
        name = os.path.basename(getattr(f, 'name', '') or 'file')
        ext = os.path.splitext(name)[1].lower()
        if ext in ALLOWED_IMAGE_EXTS:
            if size > MAX_IMAGE_BYTES:
                raise serializers.ValidationError(f'Image "{name}" exceeds the 5 MB limit.')
            normalized = normalize_image(f, max_mb=5)
            validated.append((normalized, normalized.name, MessageAttachment.FileType.IMAGE,
                              normalized.content_type, normalized.size))
        elif ext in ALLOWED_PDF_EXTS:
            if size > MAX_PDF_BYTES:
                raise serializers.ValidationError(f'PDF "{name}" exceeds the 10 MB limit.')
            f.seek(0)
            try:
                if f.read(5) != b'%PDF-':
                    raise ValueError('Missing PDF header')
                f.seek(0)
                validate_pdf(f)
                f.seek(0)
            except Exception:
                raise serializers.ValidationError(f'File "{name}" is not a valid PDF document.')
            validated.append((f, name, MessageAttachment.FileType.PDF, 'application/pdf', size))
        else:
            raise serializers.ValidationError(
                f'Unsupported file type for "{name}". Use a supported raster image or PDF.'
            )
    return validated


class MessageAttachmentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = MessageAttachment
        fields = ('id', 'original_filename', 'file_type', 'mime_type', 'file_size', 'download_url', 'created_at')

    def get_download_url(self, obj):
        request = self.context.get('request')
        path = f'/api/v1/messaging/attachments/{obj.id}/'
        return request.build_absolute_uri(path) if request else path


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.full_name', read_only=True)
    sender_role = serializers.CharField(source='sender.role', read_only=True)
    attachments = MessageAttachmentSerializer(many=True, read_only=True)
    related_pet_name = serializers.CharField(source='related_pet.name', read_only=True, default=None)
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = (
            'id', 'conversation', 'sender', 'sender_name', 'sender_role',
            'content', 'request_type', 'related_pet', 'related_pet_name',
            'request_metadata', 'client_id', 'attachments', 'is_read', 'created_at',
        )
        read_only_fields = ('id', 'conversation', 'sender', 'created_at')

    def get_is_read(self, obj):
        read_states = self.context.get('recipient_read_states')
        if read_states is None:
            return False
        sender_role = getattr(obj.sender, 'role', None)
        for rs in read_states:
            if rs.user_id == obj.sender_id:
                continue
            if sender_role == 'shelter_admin' and getattr(rs.user, 'role', None) == 'platform_admin':
                if rs.last_read_at > obj.created_at or (rs.last_read_at == obj.created_at and rs.last_read_message_id and rs.last_read_message_id >= obj.id):
                    return True
            elif sender_role == 'platform_admin' and getattr(rs.user, 'role', None) == 'shelter_admin':
                if rs.last_read_at > obj.created_at or (rs.last_read_at == obj.created_at and rs.last_read_message_id and rs.last_read_message_id >= obj.id):
                    return True
        return False


class ConversationSerializer(serializers.ModelSerializer):
    shelter_id = serializers.UUIDField(source='shelter.id', read_only=True)
    shelter_name = serializers.CharField(source='shelter.name', read_only=True)
    shelter_slug = serializers.CharField(source='shelter.slug', read_only=True)
    shelter_logo = serializers.SerializerMethodField()
    shelter_admins = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            'id', 'shelter_id', 'shelter_name', 'shelter_slug', 'shelter_logo',
            'shelter_admins', 'last_message', 'unread_count',
            'created_at', 'last_activity_at',
        )

    def get_shelter_logo(self, obj):
        request = self.context.get('request')
        return resolve_media_url(request, obj.shelter.profile_image)

    def get_shelter_admins(self, obj):
        admins = list(obj.shelter.administrators.filter(is_active=True).values('id', 'full_name', 'email'))
        if obj.shelter.owner and obj.shelter.owner.is_active:
            if not any(a['id'] == obj.shelter.owner_id for a in admins):
                admins.append({
                    'id': obj.shelter.owner_id,
                    'full_name': obj.shelter.owner.full_name,
                    'email': obj.shelter.owner.email,
                })
        return admins

    def get_last_message(self, obj):
        msg = obj.messages.order_by('-created_at').first()
        if not msg:
            return None
        preview = (msg.content or '').strip()
        if not preview and msg.attachments.exists():
            preview = '[Attachment]'
        return {
            'id': str(msg.id),
            'content': preview[:140],
            'request_type': msg.request_type,
            'sender_role': msg.sender.role,
            'sender_name': msg.sender.full_name,
            'created_at': msg.created_at,
        }

    def get_unread_count(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return 0
        rs = MessageReadState.objects.filter(conversation=obj, user=user).first()
        qs = obj.messages.exclude(sender=user)
        if user.role == 'platform_admin':
            qs = qs.filter(sender__role='shelter_admin')
        else:
            qs = qs.filter(sender__role='platform_admin')
        if rs:
            qs = qs.filter(unread_after(rs))
        return qs.count()
