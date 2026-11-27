from rest_framework import generics, permissions, filters, status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.shortcuts import get_object_or_404
from .models import Pet, Favorite
from .serializers import PetListSerializer, PetDetailSerializer, PetCreateUpdateSerializer, FavoriteSerializer
from apps.shelters.models import Shelter
from apps.core.permissions import IsShelterAdmin
from apps.core.services import log_audit_event


def _public_pets_queryset():
    return (
        Pet.objects.filter(
            is_published=True,
            is_archived=False,
            adoption_status='available',
            shelter__is_active=True,
            shelter__is_public=True,
            shelter__is_archived=False,
        )
        .exclude(shelter__verification_status=Shelter.VerificationStatus.SUSPENDED)
        .select_related('shelter', 'city')
        .prefetch_related('images')
    )


class PetListView(generics.ListAPIView):
    """Public listing of available, published pets from eligible active shelters."""
    serializer_class = PetListSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        'species', 'sex', 'size', 'age_category',
        'adoption_status', 'shelter', 'city',
        'is_vaccinated', 'is_sterilized', 'has_special_needs',
        'good_with_children', 'good_with_dogs', 'good_with_cats',
    ]
    search_fields = ['name', 'breed', 'description', 'shelter__name']
    ordering_fields = ['created_at', 'name']

    def get_queryset(self):
        return _public_pets_queryset().order_by('-created_at')


class PetDetailView(generics.RetrieveAPIView):
    """Public detail for a single pet."""
    serializer_class = PetDetailSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return (
            Pet.objects.filter(
                is_published=True,
                is_archived=False,
                shelter__is_active=True,
                shelter__is_public=True,
                shelter__is_archived=False,
            )
            .exclude(shelter__verification_status=Shelter.VerificationStatus.SUSPENDED)
            .select_related('shelter', 'city')
            .prefetch_related('images')
        )


class ShelterPetListView(generics.ListAPIView):
    """List pets for a specific shelter (public profile or assigned shelter dashboard)."""
    serializer_class = PetListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        shelter_slug = self.kwargs['shelter_slug']
        shelter = get_object_or_404(Shelter, slug=shelter_slug, is_archived=False)
        user = self.request.user

        include_all = self.request.query_params.get('all', 'false').lower() == 'true'
        is_assigned_shelter_admin = (
            user.is_authenticated
            and user.is_active
            and user.role == 'shelter_admin'
            and (shelter.administrators.filter(id=user.id).exists() or shelter.owner_id == user.id)
        )
        if include_all and is_assigned_shelter_admin:
            return (
                Pet.objects.filter(shelter=shelter)
                .select_related('shelter', 'city')
                .prefetch_related('images')
                .order_by('-created_at')
            )

        # Public visitors see available and published pets only when the shelter is active & not suspended
        if (
            not shelter.is_active
            or not shelter.is_public
            or shelter.verification_status == Shelter.VerificationStatus.SUSPENDED
        ):
            return Pet.objects.none()

        return (
            Pet.objects.filter(
                shelter=shelter,
                is_published=True,
                is_archived=False,
                adoption_status='available',
            )
            .select_related('shelter', 'city')
            .prefetch_related('images')
            .order_by('-created_at')
        )


class ShelterPetCreateView(generics.CreateAPIView):
    """Add a new pet listing under the authenticated Shelter Administrator's assigned shelter."""
    serializer_class = PetCreateUpdateSerializer
    permission_classes = [IsShelterAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def perform_create(self, serializer):
        shelter_slug = self.kwargs['shelter_slug']
        user = self.request.user
        shelter = get_object_or_404(
            Shelter,
            Q(administrators=user) | Q(owner=user),
            slug=shelter_slug,
            is_archived=False,
        )
        pet = serializer.save(shelter=shelter, city=shelter.city)
        log_audit_event(
            self.request,
            'animal_created',
            'Pet',
            pet.id,
            {'name': pet.name, 'species': pet.species, 'shelter': shelter.name},
        )


class PetUpdateView(generics.RetrieveUpdateDestroyAPIView):
    """Edit, archive, or update a pet listing (strictly assigned Shelter Administrator only)."""
    serializer_class = PetCreateUpdateSerializer
    permission_classes = [IsShelterAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        user = self.request.user
        return Pet.objects.filter(
            Q(shelter__administrators=user) | Q(shelter__owner=user),
            shelter__is_archived=False,
        ).distinct()

    def perform_update(self, serializer):
        pet = serializer.save()
        log_audit_event(
            self.request,
            'animal_updated',
            'Pet',
            pet.id,
            {'name': pet.name, 'adoption_status': pet.adoption_status, 'is_archived': pet.is_archived},
        )

    def perform_destroy(self, instance):
        # Preserve adoption history by archiving instead of hard-deleting
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


class FavoriteListView(generics.ListCreateAPIView):
    """User's favorited pets."""
    serializer_class = FavoriteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Favorite.objects.filter(user=self.request.user).select_related(
            'pet__shelter', 'pet__city'
        ).prefetch_related('pet__images')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class FavoriteToggleView(APIView):
    """Toggle a pet's favorite status for the current user."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pet_id):
        pet = get_object_or_404(Pet, id=pet_id, is_published=True, is_archived=False)
        favorite, created = Favorite.objects.get_or_create(user=request.user, pet=pet)
        if not created:
            favorite.delete()
            return Response({'favorited': False}, status=status.HTTP_200_OK)
        return Response({'favorited': True}, status=status.HTTP_201_CREATED)
