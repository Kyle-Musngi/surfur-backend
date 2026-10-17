from rest_framework import generics, permissions
from rest_framework import serializers
from .models import Event


class EventSerializer(serializers.ModelSerializer):
    shelter_name = serializers.CharField(source='host_shelter.name', read_only=True)
    city_name = serializers.CharField(source='city.name', read_only=True)

    class Meta:
        model = Event
        fields = (
            'id', 'title', 'description', 'event_type', 'status',
            'start_datetime', 'end_datetime', 'timezone',
            'venue_name', 'venue_address', 'city_name', 'maps_link',
            'contact_info', 'registration_required', 'registration_link',
            'cover_photo', 'shelter_name', 'is_published',
        )


class EventListView(generics.ListAPIView):
    serializer_class = EventSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Event.objects.filter(
            is_published=True,
            status__in=['upcoming', 'ongoing']
        ).select_related('host_shelter', 'city').order_by('start_datetime')


class EventDetailView(generics.RetrieveAPIView):
    serializer_class = EventSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Event.objects.filter(is_published=True).select_related('host_shelter', 'city')
