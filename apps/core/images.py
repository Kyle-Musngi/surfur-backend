"""Bounded raster decoding. Animated inputs intentionally become a static first frame."""
import io
import uuid
import warnings
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from rest_framework import serializers

register_heif_opener(thumbnails=False)
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.jfif', '.png', '.webp', '.gif', '.bmp',
                    '.tiff', '.tif', '.heic', '.heif', '.avif', '.ico'}
IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP', 'GIF', 'BMP', 'TIFF', 'HEIF', 'AVIF', 'ICO'}
MAX_PIXELS = 20_000_000
MAX_SIDE = 12000


def normalize_image(file, max_mb=5):
    if not file:
        return file
    if file.size > max_mb * 1024 * 1024:
        raise serializers.ValidationError(f'Image file size must not exceed {max_mb} MB.')
    if Path(file.name or '').suffix.lower() not in IMAGE_EXTENSIONS:
        raise serializers.ValidationError('Unsupported raster image format. SVG and camera RAW are not accepted.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            file.seek(0)
            with Image.open(file) as source:
                if source.format not in IMAGE_FORMATS:
                    raise serializers.ValidationError('This image encoding is unsupported.')
                if max(source.size) > MAX_SIDE or source.width * source.height > MAX_PIXELS:
                    raise serializers.ValidationError('Image exceeds the 20 megapixel or 12000 pixel side limit.')
                source.verify()
            file.seek(0)
            with Image.open(file) as source:
                source.seek(0)
                source.load()
                oriented = ImageOps.exif_transpose(source)
                transparent = 'A' in oriented.getbands() or 'transparency' in oriented.info
                converted = oriented.convert('RGBA' if transparent else 'RGB')
                converted.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
                # A fresh pixel-only image drops EXIF/GPS, ICC, comments and other metadata.
                clean = Image.frombytes(converted.mode, converted.size, converted.tobytes())
                result = io.BytesIO()
                fmt, ext, mime = ('PNG', '.png', 'image/png') if transparent else ('JPEG', '.jpg', 'image/jpeg')
                clean.save(result, format=fmt, **({'optimize': True} if transparent else {'quality': 85, 'optimize': True}))
                if result.tell() > max_mb * 1024 * 1024:
                    raise serializers.ValidationError('Converted image exceeds the upload size limit. Please use a smaller image.')
                return SimpleUploadedFile(uuid.uuid4().hex + ext, result.getvalue(), content_type=mime)
    except serializers.ValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise serializers.ValidationError('Image dimensions are too large to process safely.')
    except Exception:
        raise serializers.ValidationError('Image is corrupted, unsupported, or could not be converted safely.')
    finally:
        file.seek(0)
