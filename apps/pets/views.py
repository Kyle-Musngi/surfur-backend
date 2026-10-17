from rest_framework import generics, permissions, filters, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from .models import Pet, Favorite
from .serializers import PetListSerializer, PetDetailSerializer, PetCreateUpdateSerializer, FavoriteSerializer
from apps.shelters.models import Shelter


class PetListView(generics.ListAPIView):
    """Public listing of available, published pets."""
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
        return Pet.objects.filter(
            is_published=True,
            adoption_status='available',
        ).select_related('shelter', 'city').prefetch_related('images').order_by('-created_at')


class PetDetailView(generics.RetrieveAPIView):
    """Public detail for a single pet."""
    serializer_class = PetDetailSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Pet.objects.filter(is_published=True).select_related(
            'shelter', 'city'
        ).prefetch_related('images')


class ShelterPetListView(generics.ListAPIView):
    """List pets for a specific shelter (used by shelter public profile and shelter dashboard)."""
    serializer_class = PetListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        shelter_slug = self.kwargs['shelter_slug']
        shelter = get_object_or_404(Shelter, slug=shelter_slug)
        user = self.request.user

        # Shelter staff or platform admin viewing with all=true sees all status pets
        include_all = self.request.query_params.get('all', 'false').lower() == 'true'
        if include_all and user.is_authenticated and (user.is_platform_admin or shelter.administrators.filter(id=user.id).exists() or shelter.owner == user):
            return Pet.objects.filter(shelter=shelter).select_related('shelter', 'city').prefetch_related('images').order_by('-created_at')

        # Public visitors see available and published pets exclusively belonging to this shelter
        return Pet.objects.filter(
            shelter=shelter,
            is_published=True,
            adoption_status='available',
        ).select_related('shelter', 'city').prefetch_related('images').order_by('-created_at')


class ShelterPetCreateView(generics.CreateAPIView):
    """Add a new pet listing under a shelter."""
    serializer_class = PetCreateUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        shelter_slug = self.kwargs['shelter_slug']
        user = self.request.user
        if user.is_platform_admin:
            shelter = get_object_or_404(Shelter, slug=shelter_slug)
        else:
            shelter = get_object_or_404(Shelter, slug=shelter_slug, administrators=user)
        serializer.save(shelter=shelter, city=shelter.city)


class PetUpdateView(generics.RetrieveUpdateDestroyAPIView):
    """Edit or update a pet listing."""
    serializer_class = PetCreateUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_platform_admin:
            return Pet.objects.all()
        return Pet.objects.filter(shelter__administrators=user)


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
        pet = get_object_or_404(Pet, id=pet_id, is_published=True)
        favorite, created = Favorite.objects.get_or_create(user=request.user, pet=pet)
        if not created:
            favorite.delete()
            return Response({'favorited': False}, status=status.HTTP_200_OK)
        return Response({'favorited': True}, status=status.HTTP_201_CREATED)
