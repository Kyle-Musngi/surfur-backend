from rest_framework import generics, permissions
from rest_framework import serializers
from .models import DonationCampaign


class DonationCampaignSerializer(serializers.ModelSerializer):
    shelter_name = serializers.CharField(source='shelter.name', read_only=True)
    pet_name = serializers.CharField(source='sponsored_pet.name', read_only=True)
    progress_percent = serializers.SerializerMethodField()

    class Meta:
        model = DonationCampaign
        fields = (
            'id', 'title', 'description', 'purpose',
            'target_amount', 'confirmed_amount', 'progress_percent',
            'status', 'cover_image', 'shelter_name', 'pet_name', 'created_at',
        )

    def get_progress_percent(self, obj):
        if obj.target_amount and obj.target_amount > 0:
            return round(float(obj.confirmed_amount) / float(obj.target_amount) * 100, 1)
        return None


class CampaignListView(generics.ListAPIView):
    serializer_class = DonationCampaignSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return DonationCampaign.objects.filter(
            is_published=True, status='active'
        ).select_related('shelter', 'sponsored_pet').order_by('-created_at')


class CampaignDetailView(generics.RetrieveAPIView):
    serializer_class = DonationCampaignSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return DonationCampaign.objects.filter(is_published=True).select_related(
            'shelter', 'sponsored_pet'
        )
