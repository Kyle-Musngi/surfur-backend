from rest_framework import generics, permissions, filters, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count
from .models import Shelter
from .serializers import (
    ShelterListSerializer,
    ShelterDetailSerializer,
    ShelterRegistrationSerializer,
)
from apps.core.permissions import IsPlatformAdmin, IsShelterAdmin
from apps.core.services import log_audit_event
from apps.pets.models import Pet
from apps.adoptions.models import AdoptionInquiry
from rest_framework import serializers


class ShelterListView(generics.ListAPIView):
    """Public listing of active, published, non-suspended shelters."""
    serializer_class = ShelterListSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['animal_types', 'organization_type', 'city', 'verification_status']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']

    def get_queryset(self):
        return (
            Shelter.objects.filter(
                is_active=True,
                is_public=True,
                is_archived=False,
            )
            .exclude(verification_status=Shelter.VerificationStatus.SUSPENDED)
            .select_related('city')
            .order_by('name')
        )


class ShelterDetailView(generics.RetrieveAPIView):
    """Public detail for a single eligible shelter by slug."""
    serializer_class = ShelterDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        return (
            Shelter.objects.filter(
                is_active=True,
                is_public=True,
                is_archived=False,
            )
            .exclude(verification_status=Shelter.VerificationStatus.SUSPENDED)
            .select_related('city')
        )


class ShelterRegisterView(generics.CreateAPIView):
    """
    Restricted to Platform Administrators only.
    Public and Shelter Admin shelter registration is disabled.
    """
    serializer_class = ShelterRegistrationSerializer
    permission_classes = [IsPlatformAdmin]

    def perform_create(self, serializer):
        shelter = serializer.save()
        log_audit_event(
            self.request,
            'shelter_registered',
            'Shelter',
            shelter.id,
            {'name': shelter.name, 'slug': shelter.slug},
        )


class ShelterSelfUpdateSerializer(serializers.ModelSerializer):
    """Fields a Shelter Administrator is permitted to update on their own shelter."""
    class Meta:
        model = Shelter
        fields = (
            'description', 'mission', 'phone_number', 'email',
            'website', 'facebook_url', 'instagram_url',
            'profile_image', 'cover_image', 'operating_hours',
            'adoption_requirements', 'animal_types',
        )


class MyShelterView(APIView):
    """View or update permitted fields of the authenticated Shelter Administrator's assigned shelter."""
    permission_classes = [IsShelterAdmin]

    def _get_shelter(self, user):
        return (
            Shelter.objects.filter(
                Q(administrators=user) | Q(owner=user),
                is_archived=False,
            )
            .select_related('city')
            .first()
        )

    def get(self, request):
        shelter = self._get_shelter(request.user)
        if not shelter:
            return Response(
                {
                    'has_shelter': False,
                    'detail': 'No active shelter is currently assigned to your account. Please contact the SurFur Platform Administrator.',
                    'shelter': None,
                },
                status=status.HTTP_200_OK,
            )
        return Response(
            {
                'has_shelter': True,
                'shelter': ShelterDetailSerializer(shelter).data,
                'is_active': shelter.is_active,
                'is_public': shelter.is_public,
                'verification_status': shelter.verification_status,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        shelter = self._get_shelter(request.user)
        if not shelter:
            return Response(
                {'detail': 'No active shelter is assigned to your account.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = ShelterSelfUpdateSerializer(shelter, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_audit_event(
            request,
            'shelter_profile_updated_by_owner',
            'Shelter',
            shelter.id,
            {'name': shelter.name},
        )
        return Response(
            {
                'has_shelter': True,
                'shelter': ShelterDetailSerializer(shelter).data,
                'is_active': shelter.is_active,
                'is_public': shelter.is_public,
                'verification_status': shelter.verification_status,
            },
            status=status.HTTP_200_OK,
        )


class MyShelterStatsView(APIView):
    """Statistics & chart data for the authenticated Shelter Administrator's assigned shelter."""
    permission_classes = [IsShelterAdmin]

    def get(self, request):
        shelter = (
            Shelter.objects.filter(
                Q(administrators=request.user) | Q(owner=request.user),
                is_archived=False,
            )
            .first()
        )
        if not shelter:
            return Response(
                {'has_shelter': False, 'detail': 'No assigned shelter found.'},
                status=status.HTTP_200_OK,
            )

        pets_qs = Pet.objects.filter(shelter=shelter, is_archived=False)
        inquiries_qs = AdoptionInquiry.objects.filter(shelter=shelter)

        status_counts = dict(
            inquiries_qs.values_list('status').annotate(total=Count('id'))
        )
        species_counts = dict(
            pets_qs.values_list('species').annotate(total=Count('id'))
        )

        return Response({
            'has_shelter': True,
            'shelter_id': str(shelter.id),
            'shelter_name': shelter.name,
            'shelter_slug': shelter.slug,
            'verification_status': shelter.verification_status,
            'is_active': shelter.is_active,
            'is_public': shelter.is_public,
            'total_animals': pets_qs.count(),
            'available_animals': pets_qs.filter(adoption_status='available').count(),
            'available_dogs': pets_qs.filter(species='dog', adoption_status='available').count(),
            'available_cats': pets_qs.filter(species='cat', adoption_status='available').count(),
            'adopted_animals': pets_qs.filter(adoption_status='adopted').count(),
            'pending_applications': inquiries_qs.filter(
                status__in=['submitted', 'under_review', 'more_info', 'visit_requested']
            ).count(),
            'approved_applications': inquiries_qs.filter(status='approved').count(),
            'rejected_applications': inquiries_qs.filter(status__in=['rejected', 'declined']).count(),
            'completed_adoptions': inquiries_qs.filter(status='completed').count(),
            'total_applications': inquiries_qs.count(),
            'species_distribution': [
                {'label': 'Dogs', 'value': species_counts.get('dog', 0)},
                {'label': 'Cats', 'value': species_counts.get('cat', 0)},
                {'label': 'Other', 'value': species_counts.get('other', 0)},
            ],
            'application_status_distribution': [
                {'status': k, 'count': v} for k, v in status_counts.items()
            ],
        })
