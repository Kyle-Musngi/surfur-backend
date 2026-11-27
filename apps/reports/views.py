import secrets
from datetime import timedelta
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email as django_validate_email
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, permissions, serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdopter, IsShelterAdmin
from apps.core.services import get_client_ip, log_audit_event
from apps.core.validators import resolve_media_url, validate_ph_mobile, validate_uploaded_image
from apps.shelters.models import Shelter
from .models import StrayReport, StrayReportStatusHistory
from .services import (
    detect_potential_duplicate,
    hash_token,
    notify_stray_report_status,
    send_guest_verification_email,
    verify_token,
)


class StrayReportStatusHistorySerializer(serializers.ModelSerializer):
    assigned_organization_name = serializers.CharField(
        source='assigned_organization.name', read_only=True
    )

    class Meta:
        model = StrayReportStatusHistory
        fields = ('id', 'old_status', 'new_status', 'assigned_organization_name', 'public_note', 'timestamp')


class StrayReportSerializer(serializers.ModelSerializer):
    photo = serializers.FileField(required=False, allow_null=True, write_only=True)
    photo_url = serializers.SerializerMethodField()
    city_name = serializers.CharField(source='city.name', read_only=True)
    assigned_organization_name = serializers.CharField(
        source='assigned_organization.name', read_only=True
    )
    status_history = StrayReportStatusHistorySerializer(many=True, read_only=True)
    latest_update = serializers.SerializerMethodField()
    honeypot = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = StrayReport
        fields = (
            'id', 'report_number', 'reporter_type', 'reporter_name', 'reporter_email', 'reporter_phone',
            'preferred_contact_method', 'contact_verified',
            'animal_type', 'estimated_animal_count', 'animal_description', 'animal_condition',
            'photo', 'photo_url', 'image_urls',
            'city', 'city_name', 'barangay', 'location_description', 'additional_location_instructions',
            'latitude', 'longitude', 'sighted_at', 'urgency',
            'status', 'assigned_organization_name', 'data_processing_consent',
            'rescued_at', 'resolved_at', 'created_at', 'updated_at',
            'status_history', 'latest_update', 'honeypot',
        )
        read_only_fields = (
            'id', 'report_number', 'reporter_type', 'contact_verified',
            'status', 'rescued_at', 'resolved_at', 'created_at', 'updated_at',
        )
        extra_kwargs = {
            'photo': {'write_only': True, 'required': False, 'allow_null': True},
            'latitude': {'write_only': True, 'required': False, 'allow_null': True},
            'longitude': {'write_only': True, 'required': False, 'allow_null': True},
        }

    def get_photo_url(self, obj):
        request = self.context.get('request')
        fallback = ''
        if isinstance(obj.image_urls, list) and obj.image_urls:
            fallback = obj.image_urls[0]
        return resolve_media_url(request, obj.photo, fallback)

    def get_latest_update(self, obj):
        last = obj.status_history.last()
        if not last:
            return None
        return {
            'status': last.new_status,
            'public_note': last.public_note,
            'timestamp': last.timestamp,
        }

    def validate_photo(self, value):
        return validate_uploaded_image(value, max_mb=5)

    def validate_reporter_phone(self, value):
        return validate_ph_mobile(value)

    def validate_reporter_email(self, value):
        cleaned = (value or '').strip()
        if not cleaned or any(ch.isspace() for ch in cleaned):
            raise serializers.ValidationError(
                'Please enter a valid email address, such as name@gmail.com.'
            )
        try:
            django_validate_email(cleaned)
        except DjangoValidationError:
            raise serializers.ValidationError(
                'Please enter a valid email address, such as name@gmail.com.'
            )
        return cleaned

    def validate(self, data):
        if data.get('honeypot'):
            raise serializers.ValidationError({'detail': 'Invalid submission detected.'})
        if not data.get('data_processing_consent'):
            raise serializers.ValidationError(
                {'data_processing_consent': 'Consent is required to submit a stray report.'}
            )
        return data


class GuestTrackSerializer(serializers.ModelSerializer):
    """Safe, non-sensitive public tracking response for verified guest tracking tokens."""
    photo_url = serializers.SerializerMethodField()
    city_name = serializers.CharField(source='city.name', read_only=True)
    assigned_organization_name = serializers.CharField(
        source='assigned_organization.name', read_only=True
    )
    status_history = StrayReportStatusHistorySerializer(many=True, read_only=True)

    class Meta:
        model = StrayReport
        fields = (
            'report_number', 'reporter_type', 'contact_verified',
            'animal_type', 'estimated_animal_count', 'animal_description',
            'city_name', 'barangay', 'location_description', 'urgency',
            'status', 'assigned_organization_name', 'photo_url',
            'rescued_at', 'resolved_at', 'created_at', 'status_history',
        )

    def get_photo_url(self, obj):
        request = self.context.get('request')
        fallback = ''
        if isinstance(obj.image_urls, list) and obj.image_urls:
            fallback = obj.image_urls[0]
        return resolve_media_url(request, obj.photo, fallback)


class StrayReportCreateView(generics.CreateAPIView):
    """
    Hybrid stray report submission supporting authenticated adopters and accountable guest reporters.
    Platform Administrators and Shelter Administrators remain restricted from public reporting.
    """
    serializer_class = StrayReportSerializer
    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        user = request.user
        if user.is_authenticated and getattr(user, 'role', None) in ('platform_admin', 'shelter_admin'):
            return Response(
                {'detail': 'Administrative accounts must remain inside their dedicated dashboards.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        is_registered = bool(user.is_authenticated and getattr(user, 'role', None) == 'adopter')

        # Guest spam & rate-limit protection
        if not is_registered:
            ip = get_client_ip(request) or 'unknown'
            ip_key = f'guest_stray_ip_{ip}'
            ip_count = cache.get(ip_key, 0)
            if ip_count >= 10:
                return Response(
                    {'detail': 'Too many guest reports from this network. Please wait before submitting again.'},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            cache.set(ip_key, ip_count + 1, 3600)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)
        validated.pop('honeypot', None)

        # Duplicate submission cooldown check (exact same description & phone within 2 minutes)
        recent_cutoff = timezone.now() - timedelta(minutes=2)
        if StrayReport.objects.filter(
            reporter_phone=validated.get('reporter_phone', ''),
            animal_description=validated.get('animal_description', ''),
            created_at__gte=recent_cutoff,
        ).exists():
            return Response(
                {'detail': 'This report was just submitted. Please avoid duplicate submissions.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        raw_tracking_token = ''
        raw_verify_token = ''

        if is_registered:
            report = StrayReport.objects.create(
                **validated,
                reporter=user,
                reporter_type=StrayReport.ReporterType.REGISTERED,
                contact_verified=True,
                status=StrayReport.Status.SUBMITTED,
            )
            audit_action = 'stray_report_submitted'
        else:
            raw_tracking_token = secrets.token_urlsafe(24)
            raw_verify_token = secrets.token_urlsafe(24)
            report = StrayReport.objects.create(
                **validated,
                reporter=None,
                reporter_type=StrayReport.ReporterType.GUEST,
                contact_verified=False,
                tracking_token_hash=hash_token(raw_tracking_token),
                contact_verification_token_hash=hash_token(raw_verify_token),
                contact_verification_expires_at=timezone.now() + timedelta(hours=24),
                status=StrayReport.Status.SUBMITTED,
            )
            audit_action = 'guest_stray_report_submitted'

        if report.photo:
            photo_uri = request.build_absolute_uri(report.photo.url)
            if not report.image_urls:
                report.image_urls = [photo_uri]
                report.save(update_fields=['image_urls'])

        StrayReportStatusHistory.objects.create(
            report=report,
            old_status='',
            new_status=StrayReport.Status.SUBMITTED,
            changed_by=user if is_registered else None,
            public_note='Stray report submitted and awaiting coordinator review.',
        )

        is_dup = detect_potential_duplicate(report)
        log_audit_event(
            request if is_registered else (report.reporter_email or 'guest'),
            audit_action,
            'StrayReport',
            report.id,
            {
                'report_number': report.report_number,
                'reporter_type': report.reporter_type,
                'is_potential_duplicate': is_dup,
            },
        )
        if is_dup:
            log_audit_event(
                'system',
                'potential_duplicate_identified',
                'StrayReport',
                report.id,
                {'report_number': report.report_number},
            )

        if is_registered:
            notify_stray_report_status(report, StrayReport.Status.SUBMITTED)
        else:
            send_guest_verification_email(report, raw_verify_token)

        response_data = StrayReportSerializer(report, context={'request': request}).data
        if raw_tracking_token:
            response_data['tracking_token'] = raw_tracking_token
        return Response(response_data, status=status.HTTP_201_CREATED)


class GuestTrackReportView(APIView):
    """Securely track a guest stray report using BOTH report_number and high-entropy tracking_token."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        report_number = (request.data.get('report_number') or '').strip()
        tracking_token = (request.data.get('tracking_token') or '').strip()
        if not report_number or not tracking_token:
            return Response(
                {'detail': 'Both report reference number and tracking access token are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        report = (
            StrayReport.objects.filter(report_number__iexact=report_number)
            .select_related('city', 'assigned_organization')
            .prefetch_related('status_history__assigned_organization')
            .first()
        )
        if not report or not verify_token(tracking_token, report.tracking_token_hash):
            return Response(
                {'detail': 'Invalid report reference or tracking access token.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(GuestTrackSerializer(report, context={'request': request}).data)


class GuestVerifyContactView(APIView):
    """Verify guest reporter email ownership via expiring verification token."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        report_number = (request.data.get('report_number') or '').strip()
        token = (request.data.get('token') or '').strip()
        if not report_number or not token:
            return Response({'detail': 'Report reference and verification token are required.'}, status=status.HTTP_400_BAD_REQUEST)

        report = StrayReport.objects.filter(report_number__iexact=report_number).first()
        if not report:
            return Response({'detail': 'Invalid verification request.'}, status=status.HTTP_404_NOT_FOUND)
        if report.contact_verified:
            return Response({'detail': 'Contact email is already verified.', 'report_number': report.report_number})
        if (
            not report.contact_verification_expires_at
            or timezone.now() > report.contact_verification_expires_at
            or not verify_token(token, report.contact_verification_token_hash)
        ):
            return Response({'detail': 'Verification link is invalid or expired.'}, status=status.HTTP_400_BAD_REQUEST)

        report.contact_verified = True
        report.contact_verification_token_hash = ''
        report.save(update_fields=['contact_verified', 'contact_verification_token_hash'])

        log_audit_event(
            report.reporter_email or 'guest',
            'reporter_contact_verified',
            'StrayReport',
            report.id,
            {'report_number': report.report_number},
        )
        return Response({'detail': 'Contact email verified successfully.', 'report_number': report.report_number})


class ClaimGuestReportView(APIView):
    """Allow an authenticated adopter to link a guest report using valid tracking proof."""
    permission_classes = [IsAdopter]

    @transaction.atomic
    def post(self, request):
        report_number = (request.data.get('report_number') or '').strip()
        tracking_token = (request.data.get('tracking_token') or '').strip()
        if not report_number or not tracking_token:
            return Response({'detail': 'Report reference and tracking token are required.'}, status=status.HTTP_400_BAD_REQUEST)

        report = StrayReport.objects.filter(report_number__iexact=report_number, reporter__isnull=True).first()
        if not report or not verify_token(tracking_token, report.tracking_token_hash):
            return Response({'detail': 'Unable to verify report ownership.'}, status=status.HTTP_403_FORBIDDEN)

        if not report.contact_verified and report.reporter_email.lower() != request.user.email.lower():
            return Response(
                {'detail': 'Please verify the report contact email or use the matching account email to claim this report.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        report.reporter = request.user
        report.reporter_type = StrayReport.ReporterType.REGISTERED
        report.contact_verified = True
        report.save(update_fields=['reporter', 'reporter_type', 'contact_verified'])
        return Response({'detail': f'Report {report.report_number} linked to your account.'})


class MyReportsView(generics.ListAPIView):
    """List stray reports submitted by the authenticated adopter."""
    serializer_class = StrayReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            StrayReport.objects.filter(reporter=self.request.user)
            .select_related('city', 'assigned_organization')
            .prefetch_related('status_history__assigned_organization')
            .order_by('-created_at')
        )


class MyReportDetailView(generics.RetrieveAPIView):
    """Retrieve a single stray report owned by the authenticated adopter."""
    serializer_class = StrayReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            StrayReport.objects.filter(reporter=self.request.user)
            .select_related('city', 'assigned_organization')
            .prefetch_related('status_history__assigned_organization')
        )


class ShelterAssignedReportListView(generics.ListAPIView):
    """List stray reports assigned to the authenticated Shelter Administrator's shelter."""
    serializer_class = StrayReportSerializer
    permission_classes = [IsShelterAdmin]

    def get_queryset(self):
        user = self.request.user
        shelter_ids = Shelter.objects.filter(
            Q(administrators=user) | Q(owner=user),
            is_archived=False,
        ).values_list('id', flat=True)
        return (
            StrayReport.objects.filter(assigned_organization_id__in=shelter_ids)
            .select_related('city', 'assigned_organization')
            .prefetch_related('status_history__assigned_organization')
            .order_by('-created_at')
        )


class ShelterAssignedReportUpdateView(APIView):
    """Allow assigned Shelter Administrators to update rescue progress for their assigned stray reports."""
    permission_classes = [IsShelterAdmin]
    ALLOWED_SHELTER_STATUSES = {
        StrayReport.Status.RESCUE_IN_PROGRESS,
        StrayReport.Status.RESCUED,
        StrayReport.Status.UNABLE_TO_LOCATE,
        StrayReport.Status.RESOLVED,
    }

    @transaction.atomic
    def patch(self, request, pk):
        user = request.user
        shelter_ids = Shelter.objects.filter(
            Q(administrators=user) | Q(owner=user),
            is_archived=False,
        ).values_list('id', flat=True)

        report = StrayReport.objects.filter(
            pk=pk, assigned_organization_id__in=shelter_ids
        ).select_related('assigned_organization', 'reporter').first()
        if not report:
            return Response(
                {'detail': 'Stray report not found or not assigned to your shelter.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        new_status = request.data.get('status')
        if new_status not in self.ALLOWED_SHELTER_STATUSES:
            return Response(
                {'detail': f'Invalid status. Allowed: {sorted(self.ALLOWED_SHELTER_STATUSES)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = report.status
        public_note = (request.data.get('public_note') or '').strip()
        report.status = new_status
        now = timezone.now()
        if new_status == StrayReport.Status.RESCUED and not report.rescued_at:
            report.rescued_at = now
        if new_status == StrayReport.Status.RESOLVED and not report.resolved_at:
            report.resolved_at = now
        report.save()

        if old_status != new_status or public_note:
            StrayReportStatusHistory.objects.create(
                report=report,
                old_status=old_status,
                new_status=new_status,
                changed_by=user,
                assigned_organization=report.assigned_organization,
                public_note=public_note or f'Status updated to {report.get_status_display()}.',
            )

        notify_stray_report_status(report, new_status, old_status)
        log_audit_event(
            request,
            'stray_report_rescue_updated',
            'StrayReport',
            report.id,
            {
                'report_number': report.report_number,
                'old_status': old_status,
                'new_status': new_status,
                'shelter': report.assigned_organization.name if report.assigned_organization else '',
            },
        )
        return Response(
            StrayReportSerializer(report, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )
