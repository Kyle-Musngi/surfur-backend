import re
from urllib.parse import urlsplit
from rest_framework import serializers

PH_MOBILE_REGEX = re.compile(r'^09\d{9}$')


def validate_ph_mobile(value: str) -> str:
    cleaned = (value or '').strip()
    if not PH_MOBILE_REGEX.match(cleaned):
        raise serializers.ValidationError(
            'Please enter a valid 11-digit Philippine mobile number starting with 09.'
        )
    return cleaned


def validate_uploaded_image(file_obj, max_mb: int = 5):
    from .images import normalize_image
    return normalize_image(file_obj, max_mb=max_mb)


def validate_external_image_url(value: str) -> str:
    cleaned = (value or '').strip()
    if not cleaned:
        return ''
    if cleaned.startswith('/media/'):
        return cleaned
    parts = urlsplit(cleaned)
    if parts.scheme.lower() not in ('http', 'https') or not parts.netloc:
        raise serializers.ValidationError(
            'Please enter a valid http(s) image URL (or leave blank). Temporary blob: or data: URLs cannot be saved.'
        )
    return cleaned


def resolve_media_url(request, file_field, fallback_url: str = ''):
    if file_field and getattr(file_field, 'name', ''):
        url = file_field.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url
    return fallback_url or None

