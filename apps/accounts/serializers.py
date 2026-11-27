from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import User


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('email', 'full_name', 'password', 'password_confirm')

    def validate(self, data):
        if data['password'] != data.pop('password_confirm'):
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
        return data

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserProfileSerializer(serializers.ModelSerializer):
    assigned_shelter = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id', 'email', 'full_name', 'role', 'is_active', 'profile_photo',
            'phone_number', 'city', 'email_notifications', 'assigned_shelter', 'created_at'
        )
        read_only_fields = ('id', 'email', 'role', 'is_active', 'assigned_shelter', 'created_at')

    def get_assigned_shelter(self, obj):
        if obj.role != User.Role.SHELTER_ADMIN:
            return None
        shelter = (
            obj.administered_shelters.filter(is_archived=False).first()
            or obj.owned_shelters.filter(is_archived=False).first()
        )
        if not shelter:
            return None
        return {
            'id': str(shelter.id),
            'name': shelter.name,
            'slug': shelter.slug,
            'verification_status': shelter.verification_status,
            'is_active': shelter.is_active,
            'is_public': shelter.is_public,
            'is_archived': shelter.is_archived,
        }


class PublicUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'full_name')
