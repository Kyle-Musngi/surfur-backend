import json
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core.services import log_audit_event
from apps.notifications.models import Notification
from apps.pets.models import Pet
from apps.shelters.models import Shelter
from .models import Conversation, Message, MessageAttachment, MessageReadState
from .serializers import (
    ConversationSerializer,
    MessageSerializer,
    validate_messaging_attachments,
)


class IsAdminOrShelterAdmin(permissions.BasePermission):
    message = 'Messaging is restricted to authorized Platform and Shelter Administrators.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and getattr(user, 'role', None) in ('platform_admin', 'shelter_admin')
        )


def _get_shelter_for_admin(user):
    return (
        Shelter.objects.filter(
            Q(administrators=user) | Q(owner=user),
            is_archived=False,
        )
        .select_related('city')
        .first()
    )


def _get_authorized_conversation(user, conversation_id):
    if user.role == 'platform_admin':
        return get_object_or_404(
            Conversation.objects.select_related('shelter'),
            id=conversation_id,
        )
    return get_object_or_404(
        Conversation.objects.select_related('shelter'),
        Q(shelter__administrators=user) | Q(shelter__owner=user),
        id=conversation_id,
        shelter__is_archived=False,
    )


def _unread_count_for_user(user):
    if user.role == 'platform_admin':
        convs = Conversation.objects.select_related('shelter').all()
        total = 0
        for conv in convs:
            rs = MessageReadState.objects.filter(conversation=conv, user=user).first()
            qs = conv.messages.filter(sender__role='shelter_admin')
            if rs:
                qs = qs.filter(created_at__gt=rs.last_read_at)
            total += qs.count()
        return total

    shelter = _get_shelter_for_admin(user)
    if not shelter:
        return 0
    conv = Conversation.objects.filter(shelter=shelter).first()
    if not conv:
        return 0
    rs = MessageReadState.objects.filter(conversation=conv, user=user).first()
    qs = conv.messages.filter(sender__role='platform_admin')
    if rs:
        qs = qs.filter(created_at__gt=rs.last_read_at)
    return qs.count()


class MessagePagination(PageNumberPagination):
    page_size = 40
    page_size_query_param = 'page_size'
    max_page_size = 100


class ConversationListCreateView(APIView):
    permission_classes = [IsAdminOrShelterAdmin]

    def get(self, request):
        user = request.user
        if user.role == 'platform_admin':
            qs = Conversation.objects.select_related('shelter', 'shelter__owner').prefetch_related(
                'shelter__administrators'
            ).order_by('-last_activity_at')
            search = request.query_params.get('search', '').strip()
            if search:
                qs = qs.filter(
                    Q(shelter__name__icontains=search)
                    | Q(shelter__administrators__full_name__icontains=search)
                ).distinct()
            data = ConversationSerializer(qs, many=True, context={'request': request}).data
            unread_only = request.query_params.get('unread_only', '').lower() == 'true'
            if unread_only:
                data = [c for c in data if c['unread_count'] > 0]
            return Response({'results': data, 'count': len(data)}, status=status.HTTP_200_OK)

        shelter = _get_shelter_for_admin(user)
        if not shelter:
            return Response({'results': [], 'count': 0}, status=status.HTTP_200_OK)
        conv, _ = Conversation.objects.get_or_create(shelter=shelter)
        data = ConversationSerializer([conv], many=True, context={'request': request}).data
        return Response({'results': data, 'count': 1}, status=status.HTTP_200_OK)

    def post(self, request):
        user = request.user
        if user.role == 'platform_admin':
            shelter_id = request.data.get('shelter_id')
            if not shelter_id:
                return Response({'detail': 'shelter_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
            shelter = get_object_or_404(Shelter, id=shelter_id, is_archived=False)
        else:
            shelter = _get_shelter_for_admin(user)
            if not shelter:
                return Response(
                    {'detail': 'No active shelter is assigned to your account.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        conv, created = Conversation.objects.get_or_create(shelter=shelter)
        return Response(
            ConversationSerializer(conv, context={'request': request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ConversationDetailView(APIView):
    permission_classes = [IsAdminOrShelterAdmin]

    def get(self, request, pk):
        conv = _get_authorized_conversation(request.user, pk)
        return Response(
            ConversationSerializer(conv, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )


class ConversationMessagesView(APIView):
    permission_classes = [IsAdminOrShelterAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, pk):
        conv = _get_authorized_conversation(request.user, pk)
        read_states = list(
            MessageReadState.objects.filter(conversation=conv).select_related('user')
        )
        qs = (
            Message.objects.filter(conversation=conv)
            .select_related('sender', 'related_pet')
            .prefetch_related('attachments')
        )

        since = request.query_params.get('since', '').strip()
        if since:
            qs = qs.filter(created_at__gt=since).order_by('created_at')
            data = MessageSerializer(
                qs,
                many=True,
                context={'request': request, 'recipient_read_states': read_states},
            ).data
            return Response({'results': data, 'count': len(data)}, status=status.HTTP_200_OK)

        paginator = MessagePagination()
        page_qs = paginator.paginate_queryset(qs.order_by('-created_at'), request)
        ordered = list(reversed(page_qs))
        data = MessageSerializer(
            ordered,
            many=True,
            context={'request': request, 'recipient_read_states': read_states},
        ).data
        return paginator.get_paginated_response(data)

    @transaction.atomic
    def post(self, request, pk):
        user = request.user
        conv = _get_authorized_conversation(user, pk)

        # Basic rate limiting: max 25 messages per minute per user
        recent_cutoff = timezone.now() - timedelta(minutes=1)
        if Message.objects.filter(sender=user, created_at__gte=recent_cutoff).count() >= 25:
            return Response(
                {'detail': 'You are sending messages too quickly. Please wait a moment.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        client_id = str(request.data.get('client_id', '') or '').strip()[:64]
        if client_id:
            existing = Message.objects.filter(
                conversation=conv,
                sender=user,
                client_id=client_id,
            ).first()
            if existing:
                return Response(
                    MessageSerializer(existing, context={'request': request}).data,
                    status=status.HTTP_200_OK,
                )

        content = str(request.data.get('content', '') or '').strip()
        raw_files = request.FILES.getlist('attachments') if hasattr(request, 'FILES') else []
        validated_files = validate_messaging_attachments(raw_files)

        if not content and not validated_files:
            return Response(
                {'detail': 'Message text or at least one valid attachment is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request_type = str(request.data.get('request_type', Message.RequestType.GENERAL) or Message.RequestType.GENERAL)
        valid_types = {c[0] for c in Message.RequestType.choices}
        if request_type not in valid_types:
            request_type = Message.RequestType.GENERAL

        related_pet = None
        related_pet_id = request.data.get('related_pet')
        if related_pet_id:
            related_pet = Pet.objects.filter(id=related_pet_id, shelter=conv.shelter).first()
            if not related_pet:
                return Response(
                    {'detail': 'Selected animal does not belong to this shelter.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        raw_meta = request.data.get('request_metadata')
        metadata = {}
        if isinstance(raw_meta, dict):
            metadata = raw_meta
        elif isinstance(raw_meta, str) and raw_meta.strip():
            try:
                parsed = json.loads(raw_meta)
                if isinstance(parsed, dict):
                    metadata = parsed
            except Exception:
                metadata = {}

        msg = Message.objects.create(
            conversation=conv,
            sender=user,
            content=content,
            request_type=request_type,
            related_pet=related_pet,
            request_metadata=metadata,
            client_id=client_id,
        )

        for file_obj, orig_name, f_type, mime, size in validated_files:
            MessageAttachment.objects.create(
                message=msg,
                file=file_obj,
                original_filename=orig_name,
                file_type=f_type,
                mime_type=mime,
                file_size=size,
            )

        conv.last_activity_at = msg.created_at
        conv.save(update_fields=['last_activity_at'])

        MessageReadState.objects.update_or_create(
            conversation=conv,
            user=user,
            defaults={'last_read_message': msg, 'last_read_at': msg.created_at},
        )

        # Notify recipient(s)
        if user.role == 'shelter_admin':
            recipients = User.objects.filter(role='platform_admin', is_active=True)
            notif_title = f'New message from {conv.shelter.name}'
            notif_msg = f'{conv.shelter.name} sent a message or request to the SurFur Administrator.'
        else:
            recipients = list(conv.shelter.administrators.filter(is_active=True))
            if conv.shelter.owner and conv.shelter.owner.is_active:
                if not any(r.id == conv.shelter.owner_id for r in recipients):
                    recipients.append(conv.shelter.owner)
            notif_title = 'New message from SurFur Administrator'
            notif_msg = 'You received a new message from the SurFur Administrator.'

        for rec in recipients:
            Notification.objects.create(
                user=rec,
                notification_type='system',
                title=notif_title,
                message=notif_msg,
                related_resource_type='conversation',
                related_resource_id=str(conv.id),
            )

        audit_action_map = {
            Message.RequestType.ADD_ANIMAL: 'animal_add_requested',
            Message.RequestType.UPDATE_ANIMAL: 'animal_update_requested',
            Message.RequestType.UPDATE_SHELTER: 'shelter_update_requested',
            Message.RequestType.UPDATE_PHOTO: 'animal_photo_update_requested',
            Message.RequestType.REMOVE_ANIMAL: 'animal_removal_requested',
        }
        action_name = (
            'admin_replied_shelter'
            if user.role == 'platform_admin'
            else audit_action_map.get(request_type, 'shelter_contacted_admin')
        )
        log_audit_event(
            request,
            action_name,
            'Conversation',
            conv.id,
            {
                'shelter': conv.shelter.name,
                'request_type': request_type,
                'attachment_count': len(validated_files),
            },
        )

        read_states = list(
            MessageReadState.objects.filter(conversation=conv).select_related('user')
        )
        return Response(
            MessageSerializer(msg, context={'request': request, 'recipient_read_states': read_states}).data,
            status=status.HTTP_201_CREATED,
        )


class ConversationMarkReadView(APIView):
    permission_classes = [IsAdminOrShelterAdmin]

    def post(self, request, pk):
        conv = _get_authorized_conversation(request.user, pk)
        latest = conv.messages.order_by('-created_at').first()
        now = timezone.now()
        MessageReadState.objects.update_or_create(
            conversation=conv,
            user=request.user,
            defaults={'last_read_message': latest, 'last_read_at': now},
        )
        return Response({'status': 'ok', 'last_read_at': now}, status=status.HTTP_200_OK)


class UnreadCountView(APIView):
    permission_classes = [IsAdminOrShelterAdmin]

    def get(self, request):
        return Response({'unread_count': _unread_count_for_user(request.user)}, status=status.HTTP_200_OK)


class MessageAttachmentDownloadView(APIView):
    permission_classes = [IsAdminOrShelterAdmin]

    def get(self, request, pk):
        attachment = get_object_or_404(
            MessageAttachment.objects.select_related('message__conversation__shelter'),
            id=pk,
        )
        # Verify participant access via _get_authorized_conversation
        _get_authorized_conversation(request.user, attachment.message.conversation_id)

        response = FileResponse(
            attachment.file.open('rb'),
            content_type=attachment.mime_type or 'application/octet-stream',
        )
        disposition = 'inline' if attachment.file_type == MessageAttachment.FileType.IMAGE else 'attachment'
        response['Content-Disposition'] = f'{disposition}; filename="{attachment.original_filename}"'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
