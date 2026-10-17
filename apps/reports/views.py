from rest_framework import generics, permissions
from .models import StrayReport
from rest_framework import serializers


class StrayReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = StrayReport
        fields = (
            'id', 'report_number', 'reporter_name', 'reporter_email', 'reporter_phone',
            'animal_type', 'animal_description', 'animal_condition', 'image_urls',
            'city', 'location_description', 'sighted_at', 'urgency',
            'status', 'data_processing_consent',
        )
        read_only_fields = ('report_number', 'status')
        # NOTE: latitude/longitude intentionally excluded from public serializer


class StrayReportCreateView(generics.CreateAPIView):
    """Submit a stray animal report."""
    serializer_class = StrayReportSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        reporter = self.request.user if self.request.user.is_authenticated else None
        serializer.save(reporter=reporter)


class MyReportsView(generics.ListAPIView):
    """List reports submitted by the current user."""
    serializer_class = StrayReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return StrayReport.objects.filter(reporter=self.request.user).order_by('-created_at')
