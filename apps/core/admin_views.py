import csv
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.http import HttpResponse
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.text import slugify
from rest_framework import generics, status, serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.adoptions.models import AdoptionInquiry
from apps.core.models import AuditLog, CebuLocation, PlatformSetting
from apps.core.permissions import IsPlatformAdmin
from apps.core.serializers import CebuLocationSerializer
from apps.core.services import log_audit_event
from apps.core.validators import resolve_media_url
from apps.pets.models import Pet
from apps.pets.serializers import PetCreateUpdateSerializer, PetDetailSerializer, PetListSerializer
from apps.reports.models import StrayReport, StrayReportStatusHistory
from apps.reports.services import notify_stray_report_status
from apps.reports.views import StrayReportStatusHistorySerializer
from apps.shelters.models import Shelter


class AdminPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = 'page_size'
    max_page_size = 100


from apps.core.validators import validate_external_image_url


# --- Serializers ---

class AdminShelterSerializer(serializers.ModelSerializer):
    city_detail = CebuLocationSerializer(source='city', read_only=True)
    animals_count = serializers.SerializerMethodField()
    adoptions_count = serializers.SerializerMethodField()
    administrators_detail = serializers.SerializerMethodField()
    owner_detail = serializers.SerializerMethodField()

    class Meta:
        model = Shelter
        fields = (
            'id', 'name', 'slug', 'organization_type', 'description', 'mission',
            'address', 'barangay', 'province', 'city', 'city_detail',
            'latitude', 'longitude', 'contact_person', 'phone_number', 'email',
            'website', 'facebook_url', 'instagram_url',
            'profile_image', 'cover_image', 'animal_types',
            'operating_hours', 'adoption_requirements',
            'verification_status', 'is_demo', 'is_active', 'is_public',
            'is_archived', 'internal_notes',
            'animals_count', 'adoptions_count',
            'owner_detail', 'administrators_detail',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'slug', 'created_at', 'updated_at')

    def get_animals_count(self, obj):
        return obj.pets.filter(is_archived=False).count()

    def get_adoptions_count(self, obj):
        return obj.inquiries.count()

    def get_owner_detail(self, obj):
        if not obj.owner:
            return None
        return {'id': str(obj.owner.id), 'email': obj.owner.email, 'full_name': obj.owner.full_name}

    def get_administrators_detail(self, obj):
        return [
            {
                'id': str(u.id),
                'email': u.email,
                'full_name': u.full_name,
                'is_active': u.is_active,
            }
            for u in obj.administrators.all()
        ]

    def validate_name(self, value):
        cleaned = value.strip()
        qs = Shelter.objects.filter(name__iexact=cleaned)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('A shelter with this name already exists.')
        return cleaned

    def validate_profile_image(self, value):
        return validate_external_image_url(value)

    def validate_cover_image(self, value):
        return validate_external_image_url(value)

    def validate(self, data):
        lat = data.get('latitude', getattr(self.instance, 'latitude', None))
        lng = data.get('longitude', getattr(self.instance, 'longitude', None))
        if lat is not None:
            try:
                lat_d = Decimal(str(lat))
                if lat_d < Decimal('-90') or lat_d > Decimal('90'):
                    raise serializers.ValidationError({'latitude': 'Latitude must be between -90 and 90.'})
            except (InvalidOperation, ValueError):
                raise serializers.ValidationError({'latitude': 'Invalid latitude value.'})
        if lng is not None:
            try:
                lng_d = Decimal(str(lng))
                if lng_d < Decimal('-180') or lng_d > Decimal('180'):
                    raise serializers.ValidationError({'longitude': 'Longitude must be between -180 and 180.'})
            except (InvalidOperation, ValueError):
                raise serializers.ValidationError({'longitude': 'Invalid longitude value.'})
        return data

    def create(self, validated_data):
        name = validated_data['name']
        base_slug = slugify(name) or 'shelter'
        slug = base_slug
        counter = 1
        while Shelter.objects.filter(slug=slug).exists():
            slug = f'{base_slug}-{counter}'
            counter += 1
        validated_data['slug'] = slug
        return super().create(validated_data)


class AdminUserSerializer(serializers.ModelSerializer):
    assigned_shelter = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id', 'email', 'full_name', 'role', 'is_active',
            'phone_number', 'city', 'assigned_shelter', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'email', 'created_at', 'updated_at')

    def get_assigned_shelter(self, obj):
        shelter = (
            obj.administered_shelters.filter(is_archived=False).first()
            or obj.owned_shelters.filter(is_archived=False).first()
        )
        if not shelter:
            return None
        return {'id': str(shelter.id), 'name': shelter.name, 'slug': shelter.slug}


class AdminAdoptionMonitoringSerializer(serializers.ModelSerializer):
    """Read-only adoption monitoring serializer that protects applicant sensitive documents."""
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    pet_species = serializers.CharField(source='pet.species', read_only=True)
    shelter_name = serializers.CharField(source='shelter.name', read_only=True)
    shelter_id = serializers.UUIDField(source='shelter.id', read_only=True)
    reviewer_name = serializers.CharField(source='reviewer.full_name', read_only=True)

    class Meta:
        model = AdoptionInquiry
        fields = (
            'id', 'reference_number', 'status', 'created_at', 'updated_at',
            'applicant_name', 'applicant_city', 'housing_type', 'living_situation',
            'pet_name', 'pet_species', 'shelter_id', 'shelter_name',
            'reviewer_name', 'shelter_notes',
        )


class AdminStrayReportSerializer(serializers.ModelSerializer):
    city_name = serializers.CharField(source='city.name', read_only=True)
    assigned_organization_name = serializers.CharField(source='assigned_organization.name', read_only=True)
    photo_url = serializers.SerializerMethodField()
    status_history = StrayReportStatusHistorySerializer(many=True, read_only=True)
    public_note = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = StrayReport
        fields = (
            'id', 'report_number', 'reporter_type', 'reporter_name', 'reporter_email', 'reporter_phone',
            'preferred_contact_method', 'contact_verified',
            'is_potential_duplicate', 'duplicate_flag_reason',
            'animal_type', 'estimated_animal_count', 'animal_description', 'animal_condition',
            'photo_url', 'image_urls',
            'city', 'city_name', 'barangay', 'location_description', 'additional_location_instructions',
            'sighted_at', 'urgency',
            'status', 'assigned_organization', 'assigned_organization_name',
            'resolution_notes', 'public_note', 'rescued_at', 'resolved_at',
            'status_history', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'report_number', 'reporter_type', 'rescued_at', 'resolved_at', 'created_at', 'updated_at')

    def get_photo_url(self, obj):
        request = self.context.get('request')
        fallback = ''
        if isinstance(obj.image_urls, list) and obj.image_urls:
            fallback = obj.image_urls[0]
        return resolve_media_url(request, obj.photo, fallback)


class AdminAuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ('id', 'actor_email', 'action', 'resource_type', 'resource_id', 'metadata', 'ip_address', 'timestamp')


class PlatformSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformSetting
        fields = (
            'contact_email', 'contact_phone', 'support_desk_name',
            'shelter_onboarding_message', 'allow_public_stray_reports', 'updated_at',
        )
        read_only_fields = ('updated_at',)


# --- Views ---

class AdminDashboardView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        days = int(request.query_params.get('days', 180) or 180)
        since = timezone.now() - timedelta(days=days)

        shelters_qs = Shelter.objects.all()
        users_qs = User.objects.all()
        pets_qs = Pet.objects.filter(is_archived=False)
        adoptions_qs = AdoptionInquiry.objects.all()
        reports_qs = StrayReport.objects.all()

        # Monthly trends
        shelter_trends = list(
            shelters_qs.filter(created_at__gte=since)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
        )
        user_trends = list(
            users_qs.filter(created_at__gte=since)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
        )
        adoption_trends = list(
            adoptions_qs.filter(created_at__gte=since)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
        )

        def fmt_trend(rows):
            return [
                {'month': r['month'].strftime('%Y-%m') if r['month'] else '', 'count': r['count']}
                for r in rows
            ]

        adoption_status_dist = [
            {'status': item['status'], 'count': item['count']}
            for item in adoptions_qs.values('status').annotate(count=Count('id')).order_by('-count')
        ]

        shelter_activity = list(
            shelters_qs.filter(is_archived=False)
            .annotate(
                animals_count=Count('pets', filter=Q(pets__is_archived=False), distinct=True),
                applications_count=Count('inquiries', distinct=True),
            )
            .values('id', 'name', 'verification_status', 'animals_count', 'applications_count')
            .order_by('-applications_count', '-animals_count')[:8]
        )

        recent_logs = _enrich_audit_logs(list(AuditLog.objects.all()[:5]))

        return Response({
            'stats': {
                'total_shelters': shelters_qs.filter(is_archived=False).count(),
                'active_shelters': shelters_qs.filter(is_active=True, is_archived=False).exclude(verification_status='suspended').count(),
                'verified_shelters': shelters_qs.filter(verification_status='verified', is_archived=False).count(),
                'unpublished_shelters': shelters_qs.filter(is_public=False, is_archived=False).count(),
                'suspended_shelters': shelters_qs.filter(verification_status='suspended', is_archived=False).count(),
                'total_users': users_qs.count(),
                'shelter_admins': users_qs.filter(role=User.Role.SHELTER_ADMIN).count(),
                'adopters': users_qs.filter(role=User.Role.ADOPTER).count(),
                'total_animals': pets_qs.count(),
                'available_dogs': pets_qs.filter(species='dog', adoption_status='available').count(),
                'available_cats': pets_qs.filter(species='cat', adoption_status='available').count(),
                'adopted_animals': pets_qs.filter(adoption_status='adopted').count(),
                'total_adoptions': adoptions_qs.count(),
                'pending_adoptions': adoptions_qs.filter(status__in=['submitted', 'under_review', 'more_info', 'visit_requested']).count(),
                'approved_adoptions': adoptions_qs.filter(status='approved').count(),
                'completed_adoptions': adoptions_qs.filter(status='completed').count(),
                'pending_stray_reports': reports_qs.filter(status__in=['submitted', 'under_review']).count(),
                'total_stray_reports': reports_qs.count(),
            },
            'charts': {
                'shelter_trends': fmt_trend(shelter_trends),
                'user_trends': fmt_trend(user_trends),
                'adoption_trends': fmt_trend(adoption_trends),
                'species_distribution': [
                    {'label': 'Dogs', 'value': pets_qs.filter(species='dog').count()},
                    {'label': 'Cats', 'value': pets_qs.filter(species='cat').count()},
                    {'label': 'Other', 'value': pets_qs.filter(species='other').count()},
                ],
                'adoption_status_distribution': adoption_status_dist,
                'shelter_activity': [
                    {
                        'id': str(s['id']),
                        'name': s['name'],
                        'verification_status': s['verification_status'],
                        'animals_count': s['animals_count'],
                        'applications_count': s['applications_count'],
                    }
                    for s in shelter_activity
                ],
            },
            'recent_activity': recent_logs,
        })


class AdminShelterListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsPlatformAdmin]
    serializer_class = AdminShelterSerializer
    pagination_class = AdminPagination

    def get_queryset(self):
        qs = Shelter.objects.select_related('city', 'owner').prefetch_related('administrators').all()
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(email__icontains=search)
                | Q(contact_person__icontains=search)
                | Q(address__icontains=search)
            )
        verification = self.request.query_params.get('verification_status', '').strip()
        if verification:
            qs = qs.filter(verification_status=verification)
        is_public = self.request.query_params.get('is_public', '').strip()
        if is_public in ('true', 'false'):
            qs = qs.filter(is_public=(is_public == 'true'))
        is_active = self.request.query_params.get('is_active', '').strip()
        if is_active in ('true', 'false'):
            qs = qs.filter(is_active=(is_active == 'true'))
        is_archived = self.request.query_params.get('is_archived', 'false').strip()
        if is_archived in ('true', 'false'):
            qs = qs.filter(is_archived=(is_archived == 'true'))
        ordering = self.request.query_params.get('ordering', '-created_at')
        if ordering in ('name', '-name', 'created_at', '-created_at', 'verification_status'):
            qs = qs.order_by(ordering)
        return qs

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        publish_now = str(data.pop('publish_now', False)).lower() == 'true'
        if publish_now and data.get('verification_status') != Shelter.VerificationStatus.VERIFIED:
            data['is_public'] = False
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        shelter = serializer.save()

        log_audit_event(
            request,
            'shelter_registered',
            'Shelter',
            shelter.id,
            {
                'name': shelter.name,
                'verification_status': shelter.verification_status,
                'is_public': shelter.is_public,
            },
        )
        return Response(self.get_serializer(shelter).data, status=status.HTTP_201_CREATED)


class AdminShelterDetailUpdateView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsPlatformAdmin]
    serializer_class = AdminShelterSerializer
    queryset = Shelter.objects.select_related('city', 'owner').prefetch_related('administrators').all()

    def perform_update(self, serializer):
        shelter = serializer.save()
        log_audit_event(
            self.request,
            'shelter_updated',
            'Shelter',
            shelter.id,
            {'name': shelter.name, 'verification_status': shelter.verification_status, 'is_public': shelter.is_public},
        )


class AdminShelterActionView(APIView):
    permission_classes = [IsPlatformAdmin]

    @transaction.atomic
    def post(self, request, pk):
        shelter = get_object_or_404(Shelter, pk=pk)
        action = request.data.get('action', '').strip()
        reason = request.data.get('reason', '').strip()

        if action == 'verify':
            shelter.verification_status = Shelter.VerificationStatus.VERIFIED
        elif action == 'unverify':
            shelter.verification_status = Shelter.VerificationStatus.UNVERIFIED
            shelter.is_public = False
        elif action == 'publish':
            if shelter.verification_status != Shelter.VerificationStatus.VERIFIED:
                return Response(
                    {'detail': 'A shelter must be verified before it can be published.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if shelter.is_archived or not shelter.is_active:
                return Response(
                    {'detail': 'Archived or deactivated shelters cannot be published.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            shelter.is_public = True
        elif action == 'unpublish':
            shelter.is_public = False
        elif action == 'activate':
            shelter.is_active = True
        elif action == 'deactivate':
            shelter.is_active = False
            shelter.is_public = False
        elif action == 'suspend':
            shelter.verification_status = Shelter.VerificationStatus.SUSPENDED
            shelter.is_public = False
        elif action == 'reactivate':
            shelter.verification_status = Shelter.VerificationStatus.VERIFIED
            shelter.is_active = True
            shelter.is_public = True
        elif action == 'archive':
            shelter.is_archived = True
            shelter.is_public = False
            shelter.is_active = False
        elif action == 'unarchive':
            shelter.is_archived = False
            shelter.is_active = True
        else:
            return Response({'detail': f'Unsupported action: {action}'}, status=status.HTTP_400_BAD_REQUEST)

        shelter.save()
        log_audit_event(
            request,
            f'shelter_{action}',
            'Shelter',
            shelter.id,
            {'name': shelter.name, 'reason': reason, 'verification_status': shelter.verification_status},
        )
        return Response(AdminShelterSerializer(shelter).data, status=status.HTTP_200_OK)


class AdminShelterAdministratorsView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request, pk):
        shelter = get_object_or_404(Shelter, pk=pk)
        admins = shelter.administrators.all().order_by('full_name')
        return Response({
            'shelter_id': str(shelter.id),
            'shelter_name': shelter.name,
            'administrators': AdminUserSerializer(admins, many=True).data,
        })

    @transaction.atomic
    def post(self, request, pk):
        shelter = get_object_or_404(Shelter, pk=pk)
        mode = request.data.get('mode', 'assign')  # 'assign' or 'create'

        if mode == 'create':
            email = (request.data.get('email') or '').strip().lower()
            full_name = (request.data.get('full_name') or '').strip()
            password = request.data.get('password') or ''
            if not email or not full_name or not password:
                return Response(
                    {'detail': 'Email, full name, and password are required.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if User.objects.filter(email__iexact=email).exists():
                return Response(
                    {'detail': 'A user with this email already exists. Use assign mode instead.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                validate_password(password)
            except DjangoValidationError as exc:
                return Response({'detail': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

            user = User.objects.create_user(
                email=email,
                full_name=full_name,
                password=password,
                role=User.Role.SHELTER_ADMIN,
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
            action_name = 'shelter_admin_created_and_assigned'
        else:
            user_id = request.data.get('user_id')
            email = (request.data.get('email') or '').strip()
            if user_id:
                user = get_object_or_404(User, pk=user_id)
            elif email:
                user = get_object_or_404(User, email__iexact=email)
            else:
                return Response({'detail': 'Provide user_id or email.'}, status=status.HTTP_400_BAD_REQUEST)

            if user.role == User.Role.PLATFORM_ADMIN:
                return Response(
                    {'detail': 'Platform Administrators cannot be assigned as Shelter Administrators.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if user.role != User.Role.SHELTER_ADMIN:
                user.role = User.Role.SHELTER_ADMIN
                user.save(update_fields=['role', 'updated_at'])
            action_name = 'shelter_admin_assigned'

        shelter.administrators.add(user)
        if not shelter.owner:
            shelter.owner = user
            shelter.save(update_fields=['owner', 'updated_at'])

        log_audit_event(
            request,
            action_name,
            'Shelter',
            shelter.id,
            {'shelter': shelter.name, 'assigned_user': user.email},
        )
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)


class AdminShelterAdministratorRemoveView(APIView):
    permission_classes = [IsPlatformAdmin]

    @transaction.atomic
    def delete(self, request, pk, user_id):
        shelter = get_object_or_404(Shelter, pk=pk)
        user = get_object_or_404(User, pk=user_id)
        shelter.administrators.remove(user)
        if shelter.owner_id == user.id:
            shelter.owner = shelter.administrators.first()
            shelter.save(update_fields=['owner', 'updated_at'])
        log_audit_event(
            request,
            'shelter_admin_removed',
            'Shelter',
            shelter.id,
            {'shelter': shelter.name, 'removed_user': user.email},
        )
        return Response({'detail': 'Shelter administrator assignment removed.'}, status=status.HTTP_200_OK)


class AdminUserListView(generics.ListAPIView):
    permission_classes = [IsPlatformAdmin]
    serializer_class = AdminUserSerializer
    pagination_class = AdminPagination

    def get_queryset(self):
        qs = User.objects.prefetch_related('administered_shelters', 'owned_shelters').all()
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(full_name__icontains=search) | Q(email__icontains=search))
        role = self.request.query_params.get('role', '').strip()
        if role:
            qs = qs.filter(role=role)
        is_active = self.request.query_params.get('is_active', '').strip()
        if is_active in ('true', 'false'):
            qs = qs.filter(is_active=(is_active == 'true'))
        return qs.order_by('-created_at')


class AdminUserUpdateView(APIView):
    permission_classes = [IsPlatformAdmin]

    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if 'role' in request.data and request.data['role'] != user.role:
            return Response(
                {'detail': 'Direct role promotion or demotion via this endpoint is restricted. Use Shelter Account Assignment.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if 'is_active' in request.data:
            new_active = bool(request.data['is_active'])
            if not new_active and user.id == request.user.id:
                return Response(
                    {'detail': 'You cannot deactivate your own Platform Administrator account.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not new_active and user.role == User.Role.PLATFORM_ADMIN:
                other_active_admins = User.objects.filter(role=User.Role.PLATFORM_ADMIN, is_active=True).exclude(pk=user.pk).count()
                if other_active_admins == 0:
                    return Response(
                        {'detail': 'Cannot deactivate the last active Platform Administrator account.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            user.is_active = new_active
            user.save(update_fields=['is_active', 'updated_at'])
            log_audit_event(
                request,
                'user_activated' if new_active else 'user_deactivated',
                'User',
                user.id,
                {'target_email': user.email},
            )

        return Response(AdminUserSerializer(user).data, status=status.HTTP_200_OK)


class AdminUserPasswordResetView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_url = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
        send_mail(
            subject='SurFur Password Reset Request',
            message=f'Hello {user.full_name},\n\nA Platform Administrator initiated a password reset for your SurFur account.\nUse this link to set a new password: {reset_url}\n',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
        log_audit_event(
            request,
            'user_password_reset_initiated',
            'User',
            user.id,
            {'target_email': user.email},
        )
        return Response({'detail': f'Password reset instructions dispatched for {user.email}.'}, status=status.HTTP_200_OK)


class AdminAnimalListCreateView(generics.ListCreateAPIView):
    """Centralized Animal Management (list across all shelters + create with shelter assignment) for Platform Administrators."""
    permission_classes = [IsPlatformAdmin]
    pagination_class = AdminPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return PetCreateUpdateSerializer
        return PetListSerializer

    def get_queryset(self):
        qs = Pet.objects.select_related('shelter', 'city').prefetch_related('images').all()
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(breed__icontains=search) | Q(shelter__name__icontains=search))
        shelter_id = self.request.query_params.get('shelter', '').strip()
        if shelter_id:
            qs = qs.filter(shelter_id=shelter_id)
        species = self.request.query_params.get('species', '').strip()
        if species:
            qs = qs.filter(species=species)
        adoption_status = self.request.query_params.get('adoption_status', '').strip()
        if adoption_status:
            qs = qs.filter(adoption_status=adoption_status)
        is_archived = self.request.query_params.get('is_archived', '').strip()
        if is_archived in ('true', 'false'):
            qs = qs.filter(is_archived=(is_archived == 'true'))
        ordering = self.request.query_params.get('ordering', '-created_at')
        if ordering in ('name', '-name', 'created_at', '-created_at', 'adoption_status'):
            qs = qs.order_by(ordering)
        return qs

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        all_pets = Pet.objects.all()
        response.data['summary'] = {
            'total': all_pets.filter(is_archived=False).count(),
            'available': all_pets.filter(is_archived=False, adoption_status='available').count(),
            'pending': all_pets.filter(is_archived=False, adoption_status='pending').count(),
            'adopted': all_pets.filter(is_archived=False, adoption_status='adopted').count(),
            'archived': all_pets.filter(is_archived=True).count(),
        }
        return response

    def perform_create(self, serializer):
        shelter = serializer.validated_data.get('shelter')
        if not shelter:
            raise serializers.ValidationError({'shelter': 'Assigned Shelter is required.'})
        extra = {'city': shelter.city}
        if not shelter.is_public:
            extra['is_published'] = False
        pet = serializer.save(**extra)
        log_audit_event(
            self.request,
            'animal_created',
            'Pet',
            pet.id,
            {'name': pet.name, 'species': pet.species, 'shelter': shelter.name},
        )


class AdminAnimalDetailUpdateView(generics.RetrieveUpdateDestroyAPIView):
    """Centralized Animal detail, edit, photo management, and safe archival for Platform Administrators."""
    permission_classes = [IsPlatformAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = Pet.objects.select_related('shelter', 'city').prefetch_related('images').all()

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return PetCreateUpdateSerializer
        return PetDetailSerializer

    def perform_update(self, serializer):
        target_shelter = serializer.validated_data.get('shelter')
        save_kwargs = {}
        if target_shelter is not None:
            save_kwargs['city'] = target_shelter.city
        pet = serializer.save(**save_kwargs)
        req = self.request
        photo_changed = bool(
            req.FILES
            or req.data.get('remove_image_ids')
            or req.data.get('primary_image_id')
            or req.data.get('image_url')
        )
        log_audit_event(
            req,
            'animal_photo_updated' if photo_changed else 'animal_updated',
            'Pet',
            pet.id,
            {'name': pet.name, 'shelter': pet.shelter.name, 'adoption_status': pet.adoption_status, 'is_archived': pet.is_archived},
        )

    def perform_destroy(self, instance):
        instance.is_archived = True
        instance.is_published = False
        instance.save(update_fields=['is_archived', 'is_published', 'updated_at'])
        log_audit_event(
            self.request,
            'animal_archived',
            'Pet',
            instance.id,
            {'name': instance.name, 'shelter': instance.shelter.name},
        )


class AdminAdoptionMonitoringListView(generics.ListAPIView):
    """Strictly read-only Adoption Monitoring for Platform Administrators."""
    permission_classes = [IsPlatformAdmin]
    serializer_class = AdminAdoptionMonitoringSerializer
    pagination_class = AdminPagination

    def get_queryset(self):
        qs = AdoptionInquiry.objects.select_related('pet', 'shelter', 'reviewer').all()
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(reference_number__icontains=search)
                | Q(applicant_name__icontains=search)
                | Q(pet__name__icontains=search)
                | Q(shelter__name__icontains=search)
            )
        shelter_id = self.request.query_params.get('shelter', '').strip()
        if shelter_id:
            qs = qs.filter(shelter_id=shelter_id)
        status_filter = self.request.query_params.get('status', '').strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        date_from = self.request.query_params.get('date_from', '').strip()
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        date_to = self.request.query_params.get('date_to', '').strip()
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs.order_by('-created_at')


class AdminStrayReportListView(generics.ListAPIView):
    permission_classes = [IsPlatformAdmin]
    serializer_class = AdminStrayReportSerializer
    pagination_class = AdminPagination

    def get_queryset(self):
        qs = (
            StrayReport.objects.select_related('city', 'assigned_organization')
            .prefetch_related('status_history__assigned_organization')
            .all()
        )
        status_filter = self.request.query_params.get('status', '').strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        urgency = self.request.query_params.get('urgency', '').strip()
        if urgency:
            qs = qs.filter(urgency=urgency)
        reporter_type = self.request.query_params.get('reporter_type', '').strip()
        if reporter_type:
            qs = qs.filter(reporter_type=reporter_type)
        contact_verified = self.request.query_params.get('contact_verified', '').strip()
        if contact_verified in ('true', 'false'):
            qs = qs.filter(contact_verified=(contact_verified == 'true'))
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(report_number__icontains=search)
                | Q(animal_description__icontains=search)
                | Q(location_description__icontains=search)
            )
        return qs.order_by('-created_at')


class AdminStrayReportUpdateView(generics.UpdateAPIView):
    permission_classes = [IsPlatformAdmin]
    serializer_class = AdminStrayReportSerializer
    queryset = StrayReport.objects.select_related('reporter', 'assigned_organization').all()

    @transaction.atomic
    def perform_update(self, serializer):
        instance = self.get_object()
        old_status = instance.status
        public_note = (serializer.validated_data.pop('public_note', '') or '').strip()
        report = serializer.save()

        now = timezone.now()
        update_fields = []
        if report.status == StrayReport.Status.RESCUED and not report.rescued_at:
            report.rescued_at = now
            update_fields.append('rescued_at')
        if report.status == StrayReport.Status.RESOLVED and not report.resolved_at:
            report.resolved_at = now
            update_fields.append('resolved_at')
        if update_fields:
            report.save(update_fields=update_fields)

        if old_status != report.status or public_note:
            StrayReportStatusHistory.objects.create(
                report=report,
                old_status=old_status,
                new_status=report.status,
                changed_by=self.request.user,
                assigned_organization=report.assigned_organization,
                public_note=public_note or f'Status updated to {report.get_status_display()}.',
            )

        notify_stray_report_status(report, report.status, old_status)
        log_audit_event(
            self.request,
            'stray_report_updated',
            'StrayReport',
            report.id,
            {
                'report_number': report.report_number,
                'old_status': old_status,
                'new_status': report.status,
                'assigned_organization': report.assigned_organization.name if report.assigned_organization else '',
            },
        )


def _filtered_analytics_querysets(request):
    date_from = request.query_params.get('date_from', '').strip()
    date_to = request.query_params.get('date_to', '').strip()
    shelter_id = request.query_params.get('shelter', '').strip()
    status_filter = request.query_params.get('status', '').strip()

    shelters_qs = Shelter.objects.filter(is_archived=False)
    pets_qs = Pet.objects.filter(is_archived=False)
    adoptions_qs = AdoptionInquiry.objects.all()
    users_qs = User.objects.all()
    reports_qs = StrayReport.objects.all()

    if shelter_id:
        shelters_qs = shelters_qs.filter(id=shelter_id)
        pets_qs = pets_qs.filter(shelter_id=shelter_id)
        adoptions_qs = adoptions_qs.filter(shelter_id=shelter_id)
        reports_qs = reports_qs.filter(assigned_organization_id=shelter_id)
    if status_filter:
        reports_qs = reports_qs.filter(status=status_filter)
    if date_from:
        shelters_qs = shelters_qs.filter(created_at__date__gte=date_from)
        pets_qs = pets_qs.filter(created_at__date__gte=date_from)
        adoptions_qs = adoptions_qs.filter(created_at__date__gte=date_from)
        users_qs = users_qs.filter(created_at__date__gte=date_from)
        reports_qs = reports_qs.filter(created_at__date__gte=date_from)
    if date_to:
        shelters_qs = shelters_qs.filter(created_at__date__lte=date_to)
        pets_qs = pets_qs.filter(created_at__date__lte=date_to)
        adoptions_qs = adoptions_qs.filter(created_at__date__lte=date_to)
        users_qs = users_qs.filter(created_at__date__lte=date_to)
        reports_qs = reports_qs.filter(created_at__date__lte=date_to)

    return shelters_qs, pets_qs, adoptions_qs, users_qs, reports_qs


class AdminReportsView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        shelters_qs, pets_qs, adoptions_qs, users_qs, reports_qs = _filtered_analytics_querysets(request)

        total_adoptions = adoptions_qs.count()
        completed_adoptions = adoptions_qs.filter(status='completed').count()
        completion_rate = round((completed_adoptions / total_adoptions) * 100, 1) if total_adoptions > 0 else 0.0

        # Average rescue completion time (hours) for reports with rescued_at
        rescued_with_ts = reports_qs.filter(rescued_at__isnull=False).values_list('created_at', 'rescued_at')
        durations = [(r_at - c_at).total_seconds() / 3600.0 for c_at, r_at in rescued_with_ts if r_at >= c_at]
        avg_rescue_hours = round(sum(durations) / len(durations), 1) if durations else None

        def monthly(qs, date_field='created_at'):
            rows = (
                qs.annotate(month=TruncMonth(date_field))
                .values('month')
                .annotate(count=Count('id'))
                .order_by('month')
            )
            return [
                {'label': r['month'].strftime('%Y-%m') if r['month'] else 'Unknown', 'value': r['count']}
                for r in rows
            ]

        shelter_comparison = list(
            shelters_qs.annotate(
                animals_count=Count('pets', filter=Q(pets__is_archived=False), distinct=True),
                adoptions_count=Count('inquiries', distinct=True),
                completed_count=Count('inquiries', filter=Q(inquiries__status='completed'), distinct=True),
                assigned_reports_count=Count('assigned_reports', distinct=True),
            )
            .values('id', 'name', 'verification_status', 'animals_count', 'adoptions_count', 'completed_count', 'assigned_reports_count')
            .order_by('-adoptions_count', '-animals_count')[:12]
        )

        stray_by_location = [
            {'label': row['city__name'] or 'Unspecified', 'value': row['count']}
            for row in reports_qs.values('city__name').annotate(count=Count('id')).order_by('-count')[:10]
        ]

        stray_status_dist = [
            {'label': row['status'], 'value': row['count']}
            for row in reports_qs.values('status').annotate(count=Count('id')).order_by('-count')
        ]

        return Response({
            'shelters': {
                'total': shelters_qs.count(),
                'active': shelters_qs.filter(is_active=True).exclude(verification_status='suspended').count(),
                'inactive': shelters_qs.filter(Q(is_active=False) | Q(verification_status='suspended')).count(),
                'verified': shelters_qs.filter(verification_status='verified').count(),
                'suspended': shelters_qs.filter(verification_status='suspended').count(),
                'unpublished': shelters_qs.filter(is_public=False).count(),
            },
            'animals': {
                'total': pets_qs.count(),
                'available': pets_qs.filter(adoption_status='available').count(),
                'adopted': pets_qs.filter(adoption_status='adopted').count(),
                'dogs': pets_qs.filter(species='dog').count(),
                'cats': pets_qs.filter(species='cat').count(),
            },
            'adoptions': {
                'total': total_adoptions,
                'pending': adoptions_qs.filter(status__in=['submitted', 'under_review', 'more_info', 'visit_requested']).count(),
                'approved': adoptions_qs.filter(status='approved').count(),
                'completed': completed_adoptions,
                'rejected': adoptions_qs.filter(status__in=['rejected', 'declined']).count(),
                'completion_rate': completion_rate,
            },
            'users': {
                'total': users_qs.count(),
                'adopters': users_qs.filter(role=User.Role.ADOPTER).count(),
                'shelter_admins': users_qs.filter(role=User.Role.SHELTER_ADMIN).count(),
                'active': users_qs.filter(is_active=True).count(),
                'inactive': users_qs.filter(is_active=False).count(),
            },
            'stray_reports': {
                'total': reports_qs.count(),
                'registered_reports': reports_qs.filter(reporter_type='registered').count(),
                'guest_reports': reports_qs.filter(reporter_type='guest').count(),
                'awaiting_review': reports_qs.filter(status='submitted').count(),
                'under_review': reports_qs.filter(status='under_review').count(),
                'assigned': reports_qs.filter(status__in=['assigned', 'referred']).count(),
                'rescue_in_progress': reports_qs.filter(status='rescue_in_progress').count(),
                'in_progress': reports_qs.filter(status__in=['assigned', 'rescue_in_progress']).count(),
                'rescued': reports_qs.filter(status='rescued').count(),
                'resolved': reports_qs.filter(status='resolved').count(),
                'potential_duplicates': reports_qs.filter(is_potential_duplicate=True).count(),
                'unresolved': reports_qs.exclude(status__in=['resolved', 'rescued', 'rejected', 'duplicate', 'cancelled']).count(),
                'avg_rescue_hours': avg_rescue_hours,
            },
            'charts': {
                'monthly_shelters': monthly(shelters_qs),
                'monthly_adoptions': monthly(adoptions_qs),
                'monthly_completed_adoptions': monthly(adoptions_qs.filter(status='completed'), 'updated_at'),
                'monthly_stray_reports': monthly(reports_qs),
                'monthly_rescues': monthly(reports_qs.filter(rescued_at__isnull=False), 'rescued_at'),
                'stray_by_location': stray_by_location,
                'stray_status_distribution': stray_status_dist,
            },
            'shelter_comparison': [
                {
                    'id': str(s['id']),
                    'name': s['name'],
                    'verification_status': s['verification_status'],
                    'animals_count': s['animals_count'],
                    'adoptions_count': s['adoptions_count'],
                    'completed_count': s['completed_count'],
                    'assigned_reports_count': s['assigned_reports_count'],
                }
                for s in shelter_comparison
            ],
        })


class AdminReportsExportCSVView(APIView):
    """Export filtered platform-wide analytics summary to CSV (excludes sensitive PII)."""
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        shelters_qs, pets_qs, adoptions_qs, users_qs, reports_qs = _filtered_analytics_querysets(request)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="surfur-platform-report.csv"'
        writer = csv.writer(response)
        writer.writerow(['Category', 'Metric', 'Count'])
        writer.writerow(['Shelters', 'Total', shelters_qs.count()])
        writer.writerow(['Shelters', 'Verified', shelters_qs.filter(verification_status='verified').count()])
        writer.writerow(['Shelters', 'Suspended', shelters_qs.filter(verification_status='suspended').count()])
        writer.writerow(['Animals', 'Total', pets_qs.count()])
        writer.writerow(['Animals', 'Available', pets_qs.filter(adoption_status='available').count()])
        writer.writerow(['Animals', 'Adopted', pets_qs.filter(adoption_status='adopted').count()])
        writer.writerow(['Adoptions', 'Total Applications', adoptions_qs.count()])
        writer.writerow(['Adoptions', 'Completed', adoptions_qs.filter(status='completed').count()])
        writer.writerow(['Users', 'Total', users_qs.count()])
        writer.writerow(['Users', 'Active', users_qs.filter(is_active=True).count()])
        writer.writerow(['Stray Reports', 'Total', reports_qs.count()])
        writer.writerow(['Stray Reports', 'Successfully Rescued', reports_qs.filter(status='rescued').count()])
        writer.writerow(['Stray Reports', 'Resolved', reports_qs.filter(status='resolved').count()])
        return response


def _build_audit_queryset(request):
    qs = AuditLog.objects.all()
    search = request.query_params.get('search', '').strip()
    if search:
        matching_emails = list(
            User.objects.filter(
                Q(full_name__icontains=search) | Q(email__icontains=search)
            ).values_list('email', flat=True)
        )
        qs = qs.filter(
            Q(actor_email__icontains=search)
            | Q(actor_email__in=matching_emails)
            | Q(action__icontains=search)
            | Q(resource_type__icontains=search)
            | Q(resource_id__icontains=search)
            | Q(metadata__icontains=search)
        )
    action = request.query_params.get('action', '').strip()
    if action:
        qs = qs.filter(action=action)
    actor = request.query_params.get('actor', '').strip()
    if actor:
        qs = qs.filter(actor_email__icontains=actor)
    actor_role = request.query_params.get('actor_role', '').strip()
    if actor_role:
        if actor_role == 'system':
            qs = qs.filter(actor_email='')
        else:
            role_emails = list(User.objects.filter(role=actor_role).values_list('email', flat=True))
            qs = qs.filter(actor_email__in=role_emails)
    resource_type = request.query_params.get('resource_type', '').strip()
    if resource_type:
        qs = qs.filter(resource_type=resource_type)
    date_from = request.query_params.get('date_from', '').strip()
    if date_from:
        qs = qs.filter(timestamp__date__gte=date_from)
    date_to = request.query_params.get('date_to', '').strip()
    if date_to:
        qs = qs.filter(timestamp__date__lte=date_to)
    return qs.order_by('-timestamp')


def _enrich_audit_logs(logs):
    emails = {log.actor_email for log in logs if log.actor_email}
    users_by_email = {
        u.email.lower(): u
        for u in User.objects.filter(email__in=emails).only('id', 'email', 'full_name', 'role')
    }

    shelter_ids = [log.resource_id for log in logs if log.resource_type == 'Shelter' and log.resource_id]
    user_ids = [log.resource_id for log in logs if log.resource_type == 'User' and log.resource_id]
    pet_ids = [log.resource_id for log in logs if log.resource_type == 'Pet' and log.resource_id]
    report_ids = [log.resource_id for log in logs if log.resource_type == 'StrayReport' and log.resource_id]
    inquiry_ids = [log.resource_id for log in logs if log.resource_type == 'AdoptionInquiry' and log.resource_id]

    shelters_map = {str(s.id): s.name for s in Shelter.objects.filter(id__in=shelter_ids).only('id', 'name')}
    users_map = {str(u.id): u.full_name for u in User.objects.filter(id__in=user_ids).only('id', 'full_name')}
    pets_map = {str(p.id): p.name for p in Pet.objects.filter(id__in=pet_ids).only('id', 'name')}
    reports_map = {str(r.id): r.report_number for r in StrayReport.objects.filter(id__in=report_ids).only('id', 'report_number')}
    inquiries_map = {str(i.id): i.reference_number for i in AdoptionInquiry.objects.filter(id__in=inquiry_ids).only('id', 'reference_number')}

    blocked_keys = {'password', 'password_confirm', 'token', 'access', 'refresh', 'secret', 'reset_url', 'uid'}
    enriched = []
    for log in logs:
        email_key = (log.actor_email or '').lower()
        actor = users_by_email.get(email_key)
        if not log.actor_email:
            actor_name = 'System'
            actor_role = 'system'
        elif actor:
            actor_name = actor.full_name
            actor_role = actor.role
        else:
            actor_name = log.actor_email
            actor_role = 'unavailable'

        meta = log.metadata if isinstance(log.metadata, dict) else {}
        safe_meta = {k: v for k, v in meta.items() if str(k).lower() not in blocked_keys}

        rid = str(log.resource_id or '')
        rtype = log.resource_type
        if rtype == 'Shelter':
            resource_name = shelters_map.get(rid) or safe_meta.get('name') or 'Shelter Record'
        elif rtype == 'User':
            resource_name = users_map.get(rid) or safe_meta.get('target_email') or 'User Account'
        elif rtype == 'Pet':
            resource_name = pets_map.get(rid) or safe_meta.get('name') or 'Animal Listing'
        elif rtype == 'StrayReport':
            resource_name = reports_map.get(rid) or safe_meta.get('report_number') or 'Stray Report'
        elif rtype == 'AdoptionInquiry':
            resource_name = inquiries_map.get(rid) or safe_meta.get('reference_number') or 'Adoption Application'
        elif rtype == 'PlatformSetting':
            resource_name = 'Platform Configuration'
        else:
            resource_name = safe_meta.get('name') or rtype or 'System Record'

        enriched.append({
            'id': log.id,
            'actor_email': log.actor_email,
            'actor_name': actor_name,
            'actor_role': actor_role,
            'action': log.action,
            'resource_type': log.resource_type,
            'resource_id': log.resource_id,
            'resource_name': resource_name,
            'metadata': safe_meta,
            'timestamp': log.timestamp,
        })
    return enriched


class AdminAuditLogListView(generics.ListAPIView):
    """Immutable read-only Audit Logs with enriched actor/resource context and summary counts."""
    permission_classes = [IsPlatformAdmin]
    serializer_class = AdminAuditLogSerializer
    pagination_class = AdminPagination

    def list(self, request, *args, **kwargs):
        qs = _build_audit_queryset(request)
        summary = {
            'total_activities': qs.count(),
            'account_changes': qs.filter(resource_type='User').count(),
            'shelter_activities': qs.filter(resource_type='Shelter').count(),
            'stray_report_activities': qs.filter(resource_type='StrayReport').count(),
        }
        page = self.paginate_queryset(qs)
        if page is not None:
            data = _enrich_audit_logs(page)
            resp = self.get_paginated_response(data)
            resp.data['summary'] = summary
            return resp
        return Response({'results': _enrich_audit_logs(qs), 'summary': summary})


class AdminAuditLogExportCSVView(APIView):
    """Export filtered audit logs to CSV (excludes sensitive credentials)."""
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        qs = _build_audit_queryset(request)[:1000]
        rows = _enrich_audit_logs(list(qs))
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="surfur-audit-logs.csv"'
        writer = csv.writer(response)
        writer.writerow(['Timestamp', 'Actor Name', 'Actor Role', 'Actor Email', 'Action', 'Resource Type', 'Resource Name', 'Resource ID'])
        for r in rows:
            writer.writerow([
                r['timestamp'].isoformat() if r['timestamp'] else '',
                r['actor_name'],
                r['actor_role'],
                r['actor_email'],
                r['action'],
                r['resource_type'],
                r['resource_name'],
                r['resource_id'],
            ])
        return response


class AdminPlatformSettingsView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        obj = PlatformSetting.get_solo()
        return Response(PlatformSettingSerializer(obj).data)

    def patch(self, request):
        obj = PlatformSetting.get_solo()
        serializer = PlatformSettingSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        log_audit_event(request, 'platform_settings_updated', 'PlatformSetting', obj.pk, serializer.validated_data)
        return Response(serializer.data)

