from rest_framework import serializers
from .models import Pet, PetImage, Favorite
from apps.core.serializers import CebuLocationSerializer


class PetImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PetImage
        fields = ('id', 'image_url', 'alt_text', 'is_primary', 'display_order')


class PetListSerializer(serializers.ModelSerializer):
    primary_image = serializers.SerializerMethodField()
    shelter_name = serializers.CharField(source='shelter.name', read_only=True)
    city_name = serializers.CharField(source='city.name', read_only=True)

    class Meta:
        model = Pet
        fields = (
            'id', 'name', 'species', 'breed', 'sex', 'age_category', 'size',
            'adoption_status', 'is_published', 'shelter_name', 'city_name',
            'primary_image', 'is_vaccinated', 'is_sterilized', 'has_special_needs',
            'good_with_children', 'good_with_dogs', 'good_with_cats',
        )

    def get_primary_image(self, obj):
        img = obj.images.filter(is_primary=True).first() or obj.images.first()
        return img.image_url if img else None


class PetDetailSerializer(serializers.ModelSerializer):
    images = PetImageSerializer(many=True, read_only=True)
    city_detail = CebuLocationSerializer(source='city', read_only=True)
    shelter_name = serializers.CharField(source='shelter.name', read_only=True)
    shelter_slug = serializers.CharField(source='shelter.slug', read_only=True)

    class Meta:
        model = Pet
        fields = (
            'id', 'name', 'species', 'breed', 'sex',
            'estimated_birth_date', 'age_years', 'age_months', 'age_category',
            'size', 'color', 'description', 'personality', 'rescue_story',
            'is_vaccinated', 'is_dewormed', 'is_sterilized',
            'has_special_needs', 'special_needs_description', 'health_notes',
            'good_with_children', 'good_with_dogs', 'good_with_cats',
            'adoption_status', 'is_published',
            'shelter_name', 'shelter_slug', 'city_detail',
            'images', 'created_at', 'updated_at',
        )


class FavoriteSerializer(serializers.ModelSerializer):
    pet = PetListSerializer(read_only=True)
    pet_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Favorite
        fields = ('id', 'pet', 'pet_id', 'created_at')

    def create(self, validated_data):
        pet_id = validated_data.pop('pet_id')
        pet = Pet.objects.get(id=pet_id)
        return Favorite.objects.create(pet=pet, **validated_data)


class PetCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pet
        fields = (
            'id', 'name', 'species', 'breed', 'sex', 'size', 'color',
            'estimated_birth_date', 'age_years', 'age_months', 'age_category',
            'description', 'personality', 'rescue_story',
            'is_vaccinated', 'is_dewormed', 'is_sterilized',
            'has_special_needs', 'special_needs_description', 'health_notes',
            'good_with_children', 'good_with_dogs', 'good_with_cats',
            'adoption_status', 'is_published',
        )
