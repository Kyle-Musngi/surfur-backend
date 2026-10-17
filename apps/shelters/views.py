from rest_framework import generics, permissions, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from .models import Shelter
from .serializers import ShelterListSerializer, ShelterDetailSerializer, ShelterRegistrationSerializer


class ShelterListView(generics.ListAPIView):
    """Public listing of verified shelters."""
    serializer_class = ShelterListSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['animal_types', 'organization_type', 'city', 'verification_status']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']

    def get_queryset(self):
        return Shelter.objects.filter(
            is_active=True,
            is_public=True,
        ).select_related('city').order_by('name')


class ShelterDetailView(generics.RetrieveAPIView):
    """Public detail for a single shelter by slug."""
    serializer_class = ShelterDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        return Shelter.objects.filter(is_active=True, is_public=True).select_related('city')


class ShelterRegisterView(generics.CreateAPIView):
    """Authenticated shelter admins register their organization."""
    serializer_class = ShelterRegistrationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        user = self.request.user
        shelter = serializer.save(owner=user)
        shelter.administrators.add(user)
        if user.role == 'adopter':
            user.role = 'shelter_admin'
            user.save(update_fields=['role'])
