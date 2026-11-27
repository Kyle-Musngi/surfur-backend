import os
import re
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

PH_MOBILE_REGEX = re.compile(r'^09\d{9}$')
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
ALLOWED_IMAGE_MIME_TYPES = {'image/jpeg', 'image/jpg', 'image/png', 'image/webp'}


def validate_ph_mobile(value: str) -> str:
    cleaned = (value or '').strip()
    if not PH_MOBILE_REGEX.match(cleaned):
        raise serializers.ValidationError(
            'Please enter a valid 11-digit Philippine mobile number starting with 09.'
        )
    return cleaned


def validate_uploaded_image(file_obj, max_mb: int = 5):
    if not file_obj:
        return file_obj
    max_bytes = max_mb * 1024 * 1024
    if file_obj.size > max_bytes:
        raise serializers.ValidationError(f'Image file size must not exceed {max_mb} MB.')
    ext = os.path.splitext(getattr(file_obj, 'name', '') or '')[1].lower()
    content_type = (getattr(file_obj, 'content_type', '') or '').lower()
    if ext and ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise serializers.ValidationError('Unsupported image format. Please upload JPG, JPEG, PNG, or WebP.')
    if content_type and content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise serializers.ValidationError('Unsupported image MIME type. Please upload JPG, JPEG, PNG, or WebP.')
    try:
        pos = file_obj.tell()
        img = Image.open(file_obj)
        img.verify()
        file_obj.seek(pos)
    except (UnidentifiedImageError, Exception):
        raise serializers.ValidationError('Invalid or corrupted image file.')
    return file_obj


def resolve_media_url(request, file_field, fallback_url: str = ''):
    if file_field and getattr(file_field, 'name', ''):
        url = file_field.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url
    return fallback_url or None

