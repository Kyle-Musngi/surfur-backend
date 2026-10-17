from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from .models import AdoptionInquiry, InquiryStatusHistory
from .serializers import AdoptionInquiryCreateSerializer, AdoptionInquirySerializer
from apps.shelters.models import Shelter
from apps.notifications.models import Notification


class AdoptionInquiryCreateView(generics.CreateAPIView):
    """Submit a new adoption application (with 18+ check and supporting documents)."""
    serializer_class = AdoptionInquiryCreateSerializer
    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        inquiry = serializer.save(applicant=user)

        # Notify shelter staff
        try:
            shelter = inquiry.shelter
            admins = shelter.administrators.all()
            for admin_user in admins:
                Notification.objects.create(
                    user=admin_user,
                    notification_type='inquiry_update',
                    title=f'New Application #{inquiry.reference_number}',
                    message=f'{inquiry.applicant_name} submitted an adoption application for {inquiry.pet.name}.',
                    related_resource_type='inquiry',
                    related_resource_id=str(inquiry.id),
                )
        except Exception as e:
            print(f"Error creating notification: {e}")


class MyInquiriesView(generics.ListAPIView):
    """List the authenticated user's own applications."""
    serializer_class = AdoptionInquirySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AdoptionInquiry.objects.filter(
            applicant=self.request.user
        ).select_related('pet', 'shelter').prefetch_related('status_history').order_by('-created_at')


class InquiryDetailView(generics.RetrieveAPIView):
    """Detail of a specific application."""
    serializer_class = AdoptionInquirySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_platform_admin:
            return AdoptionInquiry.objects.all()
        if user.is_shelter_admin:
            return AdoptionInquiry.objects.filter(shelter__administrators=user)
        return AdoptionInquiry.objects.filter(applicant=user)


class ShelterInquiryListView(generics.ListAPIView):
    """Shelter admin sees applications for their shelter's pets."""
    serializer_class = AdoptionInquirySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        shelter_slug = self.kwargs['shelter_slug']
        user = self.request.user
        if user.is_platform_admin:
            shelter = get_object_or_404(Shelter, slug=shelter_slug)
        else:
            shelter = get_object_or_404(Shelter, slug=shelter_slug, administrators=user)
        return AdoptionInquiry.objects.filter(shelter=shelter).select_related('pet', 'applicant').order_by('-created_at')


class InquiryStatusUpdateView(APIView):
    """Update status of an adoption application with audit trail and pet status synchronization."""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        user = request.user
        try:
            if user.is_platform_admin:
                inquiry = AdoptionInquiry.objects.get(pk=pk)
            elif user.is_shelter_admin:
                inquiry = AdoptionInquiry.objects.get(pk=pk, shelter__administrators=user)
            else:
                return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
        except AdoptionInquiry.DoesNotExist:
            return Response({'detail': 'Not found or unauthorized for this shelter.'}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('status')
        valid_statuses = [s[0] for s in AdoptionInquiry.Status.choices]
        if new_status not in valid_statuses:
            return Response({'detail': f'Invalid status. Choose from {valid_statuses}'}, status=status.HTTP_400_BAD_REQUEST)

        old_status = inquiry.status
        notes = request.data.get('notes', '')
        inquiry.status = new_status
        if notes:
            inquiry.shelter_notes = notes
        inquiry.reviewer = user
        inquiry.save()

        # Update Pet Status if finalized or requested
        pet_status = request.data.get('pet_status')
        if pet_status and pet_status in ['available', 'pending', 'adopted', 'hold']:
            inquiry.pet.adoption_status = pet_status
            inquiry.pet.save()
        elif new_status == 'completed':
            inquiry.pet.adoption_status = 'adopted'
            inquiry.pet.save()
        elif new_status == 'approved':
            inquiry.pet.adoption_status = 'pending'
            inquiry.pet.save()

        # Log history
        InquiryStatusHistory.objects.create(
            inquiry=inquiry,
            old_status=old_status,
            new_status=new_status,
            changed_by=user,
            notes=notes,
        )

        # Notify Applicant if user account exists
        if inquiry.applicant:
            try:
                Notification.objects.create(
                    user=inquiry.applicant,
                    notification_type='inquiry_update',
                    title=f'Application Update: {inquiry.pet.name}',
                    message=f'Your adoption application #{inquiry.reference_number} is now "{inquiry.get_status_display()}". Note: {notes or "No additional notes"}',
                    related_resource_type='inquiry',
                    related_resource_id=str(inquiry.id),
                )
            except Exception as e:
                print(f"Error creating applicant notification: {e}")

        return Response({
            'status': new_status,
            'detail': 'Status updated successfully.',
            'pet_status': inquiry.pet.adoption_status
        }, status=status.HTTP_200_OK)
