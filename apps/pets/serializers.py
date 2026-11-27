import json
from django.db import transaction
from rest_framework import serializers
from .models import Pet, PetImage, Favorite
from apps.core.serializers import CebuLocationSerializer
from apps.core.validators import resolve_media_url, validate_uploaded_image
from apps.shelters.models import Shelter

MAX_ANIMAL_IMAGES = 5


class PetImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = PetImage
        fields = ('id', 'image_url', 'alt_text', 'is_primary', 'display_order')

    def get_image_url(self, obj):
        request = self.context.get('request')
        return resolve_media_url(request, obj.image_file, obj.image_url)


class PetListSerializer(serializers.ModelSerializer):
    primary_image = serializers.SerializerMethodField()
    shelter_id = serializers.UUIDField(source='shelter.id', read_only=True)
    shelter_name = serializers.CharField(source='shelter.name', read_only=True)
    shelter_slug = serializers.CharField(source='shelter.slug', read_only=True)
    city_name = serializers.CharField(source='city.name', read_only=True)

    class Meta:
        model = Pet
        fields = (
            'id', 'name', 'species', 'breed', 'sex', 'age_category', 'size',
            'adoption_status', 'is_published', 'is_archived',
            'shelter_id', 'shelter_name', 'shelter_slug', 'city_name',
            'primary_image', 'is_vaccinated', 'is_sterilized', 'has_special_needs',
            'good_with_children', 'good_with_dogs', 'good_with_cats', 'created_at',
        )

    def get_primary_image(self, obj):
        img = obj.images.filter(is_primary=True).first() or obj.images.first()
        if not img:
            return None
        request = self.context.get('request')
        return resolve_media_url(request, img.image_file, img.image_url)


class PetDetailSerializer(serializers.ModelSerializer):
    images = PetImageSerializer(many=True, read_only=True)
    primary_image = serializers.SerializerMethodField()
    city_detail = CebuLocationSerializer(source='city', read_only=True)
    shelter_id = serializers.UUIDField(source='shelter.id', read_only=True)
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
            'adoption_status', 'is_published', 'is_archived',
            'shelter_id', 'shelter_name', 'shelter_slug', 'city_detail',
            'primary_image', 'images', 'created_at', 'updated_at',
        )

    def get_primary_image(self, obj):
        img = obj.images.filter(is_primary=True).first() or obj.images.first()
        if not img:
            return None
        request = self.context.get('request')
        return resolve_media_url(request, img.image_file, img.image_url)


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
    def save(self, **kwargs):
        self._written_files = []
        try:
            return super().save(**kwargs)
        except Exception:
            # SQL rollback does not undo storage writes. Remove only files from this attempt.
            for storage, name in self._written_files:
                storage.delete(name)
            raise

    shelter = serializers.PrimaryKeyRelatedField(
        queryset=Shelter.objects.filter(is_archived=False),
        required=False,
    )
    shelter_name = serializers.CharField(source='shelter.name', read_only=True)
    shelter_slug = serializers.CharField(source='shelter.slug', read_only=True)
    image_url = serializers.URLField(required=False, allow_blank=True, write_only=True)
    uploaded_image = serializers.FileField(required=False, allow_null=True, write_only=True)
    primary_image_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    primary_image_index = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    remove_image_ids = serializers.CharField(required=False, allow_blank=True, write_only=True)
    images = PetImageSerializer(many=True, read_only=True)

    class Meta:
        model = Pet
        fields = (
            'id', 'shelter', 'shelter_name', 'shelter_slug',
            'name', 'species', 'breed', 'sex', 'size', 'color',
            'estimated_birth_date', 'age_years', 'age_months', 'age_category',
            'description', 'personality', 'rescue_story',
            'is_vaccinated', 'is_dewormed', 'is_sterilized',
            'has_special_needs', 'special_needs_description', 'health_notes',
            'good_with_children', 'good_with_dogs', 'good_with_cats',
            'adoption_status', 'is_published', 'is_archived',
            'image_url', 'uploaded_image', 'primary_image_id',
            'primary_image_index', 'remove_image_ids', 'images',
        )

    def _get_uploaded_files(self):
        if hasattr(self, '_normalized_files'):
            return list(self._normalized_files)
        request = self.context.get('request')
        files = []
        if request is not None and hasattr(request, 'FILES'):
            files.extend(request.FILES.getlist('uploaded_images'))
        return files

    def _parse_remove_ids(self, raw):
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [int(x) for x in parsed]
        except Exception:
            pass
        return [int(x.strip()) for x in str(raw).split(',') if x.strip().isdigit()]

    def validate_uploaded_image(self, value):
        return validate_uploaded_image(value, max_mb=5)

    def validate_shelter(self, shelter):
        if shelter.is_archived or not shelter.is_active or shelter.verification_status == Shelter.VerificationStatus.SUSPENDED:
            raise serializers.ValidationError(
                'Animals cannot be assigned to an inactive, suspended, or archived shelter.'
            )
        if self.instance and shelter.id != self.instance.shelter_id:
            if self.instance.inquiries.exists():
                raise serializers.ValidationError(
                    'Cannot reassign an animal with existing adoption applications or history to another shelter.'
                )
        return shelter

    def validate(self, data):
        files = self._get_uploaded_files()

        single = data.get('uploaded_image')
        new_count = len(files) + (1 if single else 0) + (1 if data.get('image_url') else 0)
        remove_ids = self._parse_remove_ids(data.get('remove_image_ids', ''))

        existing_count = self.instance.images.exclude(id__in=remove_ids).count() if self.instance else 0
        total_after = existing_count + new_count
        if total_after > MAX_ANIMAL_IMAGES:
            raise serializers.ValidationError(
                {'uploaded_images': f'Maximum {MAX_ANIMAL_IMAGES} photographs allowed per animal.'}
            )

        self._normalized_files = [validate_uploaded_image(f, max_mb=5) for f in files]

        requested_status = data.get('adoption_status')
        if requested_status == 'adopted':
            has_completed = bool(self.instance and self.instance.inquiries.filter(status='completed').exists())
            if not has_completed:
                raise serializers.ValidationError(
                    {'adoption_status': 'Adopted status can only be set through an authorized Shelter Administrator\'s adoption completion workflow.'}
                )
        if self.instance and requested_status and requested_status != self.instance.adoption_status:
            if self.instance.inquiries.filter(status='completed').exists() and requested_status != 'adopted':
                raise serializers.ValidationError(
                    {'adoption_status': 'Cannot change status of an animal with a completed adoption record.'}
                )
            if self.instance.inquiries.filter(status='approved').exists() and requested_status == 'available':
                raise serializers.ValidationError(
                    {'adoption_status': 'Cannot mark an animal available while an adoption application is approved.'}
                )

        target_shelter = data.get('shelter') or (self.instance.shelter if self.instance else None)
        if target_shelter and (
            not target_shelter.is_public
            or not target_shelter.is_active
            or target_shelter.verification_status == Shelter.VerificationStatus.SUSPENDED
        ):
            data['is_published'] = False

        is_published = data.get('is_published', self.instance.is_published if self.instance else False)
        if self.instance and is_published and remove_ids and total_after == 0:
            raise serializers.ValidationError(
                {'remove_image_ids': 'A published animal listing must retain at least one photograph.'}
            )
        return data

    def _apply_images(self, pet, validated_data, image_url, uploaded_image, primary_id, primary_idx, remove_ids):
        if remove_ids:
            for img in pet.images.filter(id__in=remove_ids):
                if img.image_file:
                    storage, name = img.image_file.storage, img.image_file.name
                    transaction.on_commit(lambda storage=storage, name=name: storage.delete(name))
                img.delete()

        files = self._get_uploaded_files()
        if uploaded_image:
            files.insert(0, uploaded_image)

        created_images = []
        has_existing_primary = pet.images.filter(is_primary=True).exists()
        for idx, f in enumerate(files):
            make_primary = (primary_idx is not None and idx == primary_idx) or (
                primary_idx is None and primary_id is None and not has_existing_primary and idx == 0
            )
            image = PetImage(pet=pet, is_primary=make_primary)
            image.image_file.save(f.name, f, save=False)
            self._written_files.append((image.image_file.storage, image.image_file.name))
            image.save()
            created_images.append(image)

        if image_url and not files:
            PetImage.objects.create(
                pet=pet,
                image_url=image_url,
                is_primary=not has_existing_primary and primary_id is None,
            )

        if primary_id is not None:
            target = pet.images.filter(id=primary_id).first()
            if target:
                target.is_primary = True
                target.save()

    @transaction.atomic
    def create(self, validated_data):
        image_url = validated_data.pop('image_url', '').strip()
        uploaded_image = validated_data.pop('uploaded_image', None)
        primary_id = validated_data.pop('primary_image_id', None)
        primary_idx = validated_data.pop('primary_image_index', None)
        remove_ids = self._parse_remove_ids(validated_data.pop('remove_image_ids', ''))
        pet = super().create(validated_data)
        self._apply_images(pet, validated_data, image_url, uploaded_image, primary_id, primary_idx, remove_ids)
        return pet

    @transaction.atomic
    def update(self, instance, validated_data):
        image_url = validated_data.pop('image_url', '').strip()
        uploaded_image = validated_data.pop('uploaded_image', None)
        primary_id = validated_data.pop('primary_image_id', None)
        primary_idx = validated_data.pop('primary_image_index', None)
        remove_ids = self._parse_remove_ids(validated_data.pop('remove_image_ids', ''))
        pet = super().update(instance, validated_data)
        self._apply_images(pet, validated_data, image_url, uploaded_image, primary_id, primary_idx, remove_ids)
        return pet
