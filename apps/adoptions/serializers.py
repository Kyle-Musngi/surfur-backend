import datetime
from rest_framework import serializers
from .models import AdoptionInquiry, InquiryStatusHistory
from apps.pets.serializers import PetListSerializer
from apps.shelters.serializers import ShelterListSerializer
from django.utils import timezone


class InquiryStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source='changed_by.full_name', read_only=True)

    class Meta:
        model = InquiryStatusHistory
        fields = ('id', 'old_status', 'new_status', 'notes', 'changed_by_name', 'timestamp')


class AdoptionInquiryCreateSerializer(serializers.ModelSerializer):
    shelter = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = AdoptionInquiry
        fields = (
            'id', 'reference_number', 'pet', 'shelter',
            'applicant_name', 'applicant_email', 'applicant_phone', 'applicant_city',
            'date_of_birth', 'occupation', 'contact_preference',
            'housing_type', 'living_situation',
            'proof_of_id', 'proof_of_address', 'proof_of_income',
            'proof_of_housing', 'home_environment_media',
            'has_existing_pets', 'existing_pets_description',
            'has_owned_pets_before', 'vet_reference_name', 'vet_reference_contact',
            'has_children', 'pet_care_experience', 'reason_for_adopting',
            'long_term_care_acknowledgment',
            'data_processing_consent', 'responsible_adoption_agreement',
        )
        read_only_fields = ('id', 'reference_number', 'shelter')

    def validate(self, data):
        # 1. 18+ Legal Age Validation
        dob = data.get('date_of_birth')
        if not dob:
            raise serializers.ValidationError(
                {'date_of_birth': 'Date of birth is required to verify the 18+ legal age requirement.'}
            )

        today = datetime.date.today()
        # Calculate exact age
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < 18:
            raise serializers.ValidationError(
                {'date_of_birth': f'You must be at least 18 years old to adopt an animal. (Calculated age: {age} years old)'}
            )

        # 2. Consent Validations
        if not data.get('data_processing_consent'):
            raise serializers.ValidationError(
                {'data_processing_consent': 'You must consent to data processing under RA 10173 to submit an application.'}
            )
        if not data.get('responsible_adoption_agreement'):
            raise serializers.ValidationError(
                {'responsible_adoption_agreement': 'You must sign/agree to the responsible adoption covenant.'}
            )

        # 3. Check pet adoption status
        pet = data.get('pet')
        if pet and pet.adoption_status not in ['available', 'pending']:
            raise serializers.ValidationError(
                {'pet': f'Pet "{pet.name}" is currently {pet.get_adoption_status_display()} and not open for applications.'}
            )

        return data

    def create(self, validated_data):
        if not validated_data.get('shelter') and validated_data.get('pet'):
            validated_data['shelter'] = validated_data['pet'].shelter
        validated_data['consent_timestamp'] = timezone.now()
        return super().create(validated_data)


class AdoptionInquirySerializer(serializers.ModelSerializer):
    status_history = InquiryStatusHistorySerializer(many=True, read_only=True)
    pet = PetListSerializer(read_only=True)
    pet_name = serializers.CharField(source='pet.name', read_only=True)
    shelter_name = serializers.CharField(source='shelter.name', read_only=True)
    shelter_slug = serializers.CharField(source='shelter.slug', read_only=True)
    reviewer_name = serializers.CharField(source='reviewer.full_name', read_only=True)

    class Meta:
        model = AdoptionInquiry
        fields = (
            'id', 'reference_number', 'status', 'created_at', 'updated_at',
            'applicant', 'applicant_name', 'applicant_email', 'applicant_phone', 'applicant_city',
            'date_of_birth', 'occupation', 'contact_preference',
            'housing_type', 'living_situation',
            'proof_of_id', 'proof_of_address', 'proof_of_income',
            'proof_of_housing', 'home_environment_media',
            'has_existing_pets', 'existing_pets_description',
            'has_owned_pets_before', 'vet_reference_name', 'vet_reference_contact',
            'has_children', 'pet_care_experience', 'reason_for_adopting',
            'long_term_care_acknowledgment',
            'shelter_notes', 'reviewer_name',
            'pet', 'pet_name', 'shelter_name', 'shelter_slug',
            'status_history',
        )
        read_only_fields = ('id', 'reference_number', 'status', 'created_at', 'updated_at', 'shelter_notes')
