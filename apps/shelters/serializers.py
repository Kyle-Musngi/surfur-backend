from rest_framework import serializers
from .models import Shelter, ShelterVerification
from apps.core.serializers import CebuLocationSerializer


class ShelterListSerializer(serializers.ModelSerializer):
    city_detail = CebuLocationSerializer(source='city', read_only=True)
    available_pets_count = serializers.ReadOnlyField()

    class Meta:
        model = Shelter
        fields = (
            'id', 'name', 'slug', 'organization_type', 'description',
            'city_detail', 'latitude', 'longitude',
            'phone_number', 'email', 'website', 'facebook_url',
            'profile_image', 'cover_image', 'animal_types',
            'verification_status', 'is_demo', 'available_pets_count',
        )


class ShelterDetailSerializer(serializers.ModelSerializer):
    city_detail = CebuLocationSerializer(source='city', read_only=True)
    available_pets_count = serializers.ReadOnlyField()

    class Meta:
        model = Shelter
        fields = (
            'id', 'name', 'slug', 'organization_type', 'description', 'mission',
            'address', 'city_detail', 'latitude', 'longitude',
            'phone_number', 'email', 'website', 'facebook_url', 'instagram_url',
            'profile_image', 'cover_image', 'animal_types',
            'operating_hours', 'adoption_requirements',
            'verification_status', 'is_demo', 'available_pets_count', 'created_at',
        )


class ShelterRegistrationSerializer(serializers.ModelSerializer):
    """Used when a shelter admin registers their organization."""
    contact_person = serializers.CharField(required=False, allow_blank=True, write_only=True)
    postal_code = serializers.CharField(required=False, allow_blank=True, write_only=True)
    province = serializers.CharField(required=False, allow_blank=True, default='Cebu', write_only=True)
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    verification_document_url = serializers.CharField(required=False, allow_blank=True, write_only=True)
    verification_notes = serializers.CharField(required=False, allow_blank=True, write_only=True)
    confirmation_accurate = serializers.BooleanField(required=True, write_only=True)
    privacy_consent = serializers.BooleanField(required=True, write_only=True)

    class Meta:
        model = Shelter
        fields = (
            'id', 'name', 'slug', 'organization_type', 'description', 'mission',
            'address', 'city', 'latitude', 'longitude',
            'phone_number', 'email', 'website', 'facebook_url', 'instagram_url',
            'profile_image', 'cover_image',
            'animal_types', 'adoption_requirements',
            'contact_person', 'postal_code', 'province',
            'verification_document_url', 'verification_notes',
            'confirmation_accurate', 'privacy_consent',
            'verification_status', 'created_at',
        )
        read_only_fields = ('id', 'slug', 'verification_status', 'created_at')

    def validate_confirmation_accurate(self, value):
        if not value:
            raise serializers.ValidationError('You must confirm that all submitted information is accurate.')
        return value

    def validate_privacy_consent(self, value):
        if not value:
            raise serializers.ValidationError('You must consent to the privacy policy to submit a registration.')
        return value

    def validate_city(self, value):
        if not value.is_active:
            raise serializers.ValidationError('This location is not currently serviced.')
        return value

    def validate_name(self, value):
        cleaned_name = value.strip()
        if Shelter.objects.filter(name__iexact=cleaned_name).exists():
            raise serializers.ValidationError('An organization with this name has already been registered.')
        return cleaned_name

    def create(self, validated_data):
        from django.utils.text import slugify
        from decimal import Decimal
        import uuid as _uuid

        contact_person = validated_data.pop('contact_person', '')
        postal_code = validated_data.pop('postal_code', '')
        province = validated_data.pop('province', 'Cebu')
        verification_doc = validated_data.pop('verification_document_url', '')
        verification_notes = validated_data.pop('verification_notes', '')
        validated_data.pop('confirmation_accurate', None)
        validated_data.pop('privacy_consent', None)

        # Append postal code & province to address if provided
        address_parts = [validated_data.get('address', '').strip()]
        if postal_code and postal_code.strip():
            address_parts.append(f"Postal Code: {postal_code.strip()}")
        if province and province.strip() and 'Cebu' not in address_parts[0]:
            address_parts.append(province.strip())
        validated_data['address'] = ', '.join([p for p in address_parts if p])

        # Auto-compute coordinates if missing or zero
        city = validated_data.get('city')
        lat = validated_data.get('latitude')
        lng = validated_data.get('longitude')
        try:
            dec_lat = Decimal(str(lat)) if lat is not None else Decimal('0')
            dec_lng = Decimal(str(lng)) if lng is not None else Decimal('0')
        except Exception:
            dec_lat = Decimal('0')
            dec_lng = Decimal('0')

        if dec_lat == 0 or dec_lng == 0:
            if city and city.latitude and city.longitude:
                validated_data['latitude'] = city.latitude
                validated_data['longitude'] = city.longitude
            else:
                validated_data['latitude'] = Decimal('10.3157000')
                validated_data['longitude'] = Decimal('123.8854000')

        # Always start at PENDING review
        validated_data['verification_status'] = Shelter.VerificationStatus.PENDING

        name = validated_data['name']
        base_slug = slugify(name)
        slug = base_slug
        counter = 1
        while Shelter.objects.filter(slug=slug).exists():
            slug = f'{base_slug}-{counter}'
            counter += 1
        validated_data['slug'] = slug

        shelter = super().create(validated_data)

        # Create corresponding verification record for administrators to review
        evidence_list = []
        if verification_doc and verification_doc.strip():
            evidence_list.append(verification_doc.strip())

        review_note_parts = []
        if contact_person and contact_person.strip():
            review_note_parts.append(f"Contact Person: {contact_person.strip()}")
        if verification_notes and verification_notes.strip():
            review_note_parts.append(verification_notes.strip())
        final_notes = " | ".join(review_note_parts) or "Submitted via SurFur shelter registration form."

        ShelterVerification.objects.create(
            shelter=shelter,
            submitted_evidence=evidence_list,
            notes_from_shelter=final_notes,
            review_status=ShelterVerification.ReviewStatus.PENDING,
        )

        return shelter


class ShelterVerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShelterVerification
        fields = (
            'id', 'shelter', 'submitted_evidence', 'notes_from_shelter',
            'review_status', 'review_notes', 'submitted_at', 'reviewed_at',
        )
        read_only_fields = ('review_status', 'review_notes', 'submitted_at', 'reviewed_at')
