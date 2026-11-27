from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from .models import AdoptionInquiry, InquiryStatusHistory
from .serializers import AdoptionInquiryCreateSerializer, AdoptionInquirySerializer
from apps.shelters.models import Shelter
from apps.pets.models import Pet
from apps.notifications.models import Notification
from apps.core.permissions import IsShelterAdmin
from apps.core.services import log_audit_event


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
        except Exception:
            pass


class MyInquiriesView(generics.ListAPIView):
    """List the authenticated user's own applications."""
    serializer_class = AdoptionInquirySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AdoptionInquiry.objects.filter(
            applicant=self.request.user
        ).select_related('pet', 'shelter').prefetch_related('status_history').order_by('-created_at')


class InquiryDetailView(generics.RetrieveAPIView):
    """Detail of a specific application (read-only)."""
    serializer_class = AdoptionInquirySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'platform_admin':
            return AdoptionInquiry.objects.all()
        if user.role == 'shelter_admin':
            return AdoptionInquiry.objects.filter(
                Q(shelter__administrators=user) | Q(shelter__owner=user)
            ).distinct()
        return AdoptionInquiry.objects.filter(applicant=user)


class ShelterInquiryListView(generics.ListAPIView):
    """Shelter admin sees applications for their assigned shelter's pets."""
    serializer_class = AdoptionInquirySerializer
    permission_classes = [IsShelterAdmin]

    def get_queryset(self):
        shelter_slug = self.kwargs['shelter_slug']
        user = self.request.user
        shelter = get_object_or_404(
            Shelter,
            Q(administrators=user) | Q(owner=user),
            slug=shelter_slug,
            is_archived=False,
        )
        return (
            AdoptionInquiry.objects.filter(shelter=shelter)
            .select_related('pet', 'applicant')
            .prefetch_related('status_history')
            .order_by('-created_at')
        )


class InquiryStatusUpdateView(APIView):
    """
    Update status of an adoption application with audit trail and pet status synchronization.
    Strictly restricted to assigned Shelter Administrators (Platform Admins cannot approve/reject).
    """
    permission_classes = [IsShelterAdmin]

    @transaction.atomic
    def patch(self, request, pk):
        user = request.user
        inquiry = (
            AdoptionInquiry.objects.filter(
                Q(shelter__administrators=user) | Q(shelter__owner=user),
                pk=pk,
            )
            .select_related('pet', 'shelter')
            .first()
        )
        if not inquiry:
            return Response(
                {'detail': 'Not found or unauthorized for this shelter.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        new_status = request.data.get('status')
        valid_statuses = [s[0] for s in AdoptionInquiry.Status.choices]
        if new_status not in valid_statuses:
            return Response(
                {'detail': f'Invalid status. Choose from {valid_statuses}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if inquiry.status == AdoptionInquiry.Status.COMPLETED and new_status == AdoptionInquiry.Status.COMPLETED:
            return Response(
                {'detail': 'This adoption has already been marked as completed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pet = Pet.objects.select_for_update().get(pk=inquiry.pet_id)

        if new_status == AdoptionInquiry.Status.COMPLETED:
            if pet.adoption_status == 'adopted' or AdoptionInquiry.objects.filter(
                pet=pet, status=AdoptionInquiry.Status.COMPLETED
            ).exclude(pk=inquiry.pk).exists():
                return Response(
                    {'detail': 'This animal has already been adopted.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        old_status = inquiry.status
        notes = request.data.get('notes', '')
        inquiry.status = new_status
        if notes:
            inquiry.shelter_notes = notes
        inquiry.reviewer = user
        inquiry.save()

        # Update Pet Status if finalized or requested
        pet_status = request.data.get('pet_status')
        if new_status == 'completed':
            pet.adoption_status = 'adopted'
            pet.save(update_fields=['adoption_status', 'updated_at'])
            AdoptionInquiry.objects.filter(
                pet=pet,
                status__in=['submitted', 'under_review', 'more_info', 'visit_requested', 'approved'],
            ).exclude(pk=inquiry.pk).update(status=AdoptionInquiry.Status.DECLINED)
        elif pet_status and pet_status in ['available', 'pending', 'hold', 'unavailable']:
            pet.adoption_status = pet_status
            pet.save(update_fields=['adoption_status', 'updated_at'])
        elif new_status == 'approved':
            pet.adoption_status = 'pending'
            pet.save(update_fields=['adoption_status', 'updated_at'])

        # Log history
        InquiryStatusHistory.objects.create(
            inquiry=inquiry,
            old_status=old_status,
            new_status=new_status,
            changed_by=user,
            notes=notes,
        )

        audit_action_map = {
            'under_review': 'adoption_reviewed',
            'approved': 'adoption_approved',
            'rejected': 'adoption_rejected',
            'declined': 'adoption_rejected',
            'completed': 'adoption_completed',
        }
        log_audit_event(
            request,
            audit_action_map.get(new_status, 'adoption_progress_updated'),
            'AdoptionInquiry',
            inquiry.id,
            {
                'reference_number': inquiry.reference_number,
                'old_status': old_status,
                'new_status': new_status,
                'shelter': inquiry.shelter.name,
            },
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
            except Exception:
                pass

        return Response({
            'status': new_status,
            'detail': 'Status updated successfully.',
            'pet_status': inquiry.pet.adoption_status,
        }, status=status.HTTP_200_OK)
