import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.core.images import normalize_image
from apps.core.models import CebuLocation
from apps.messaging.serializers import validate_messaging_attachments
from apps.pets.models import Pet, PetImage
from apps.shelters.models import Shelter

FORMATS = {'jpg': 'JPEG', 'jpeg': 'JPEG', 'jfif': 'JPEG', 'png': 'PNG',
           'webp': 'WEBP', 'gif': 'GIF', 'bmp': 'BMP', 'tiff': 'TIFF',
           'tif': 'TIFF', 'heic': 'HEIF', 'heif': 'HEIF', 'avif': 'AVIF', 'ico': 'ICO'}


def encoded(ext, **options):
    buffer = io.BytesIO()
    Image.new('RGB', (32, 24), (230, 50, 80)).save(buffer, format=FORMATS[ext.lower()], **options)
    return SimpleUploadedFile('photo.' + ext, buffer.getvalue(), content_type='application/octet-stream')


class ImageNormalizationTests(SimpleTestCase):
    def test_every_real_encoding_with_both_extension_cases(self):
        for ext, actual in FORMATS.items():
            for spelling in (ext, ext.upper()):
                with self.subTest(extension=spelling):
                    upload = encoded(spelling)
                    with Image.open(upload) as original:
                        self.assertEqual(original.format, actual)
                    result = normalize_image(upload)
                    with Image.open(result) as image:
                        self.assertIn(image.format, ('JPEG', 'PNG'))
                        image.load()
                        self.assertFalse(image.getexif())
                    self.assertRegex(result.name, r'^[0-9a-f]{32}\.(jpg|png)$')
                    self.assertIn(result.content_type, ('image/jpeg', 'image/png'))

    def test_orientation_and_sensitive_metadata_removed(self):
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = 'Sensitive private location comment'
        exif[34853] = {1: 'N', 2: (10.0, 1.0, 1.0), 3: 'E', 4: (123.0, 1.0, 1.0)}
        result = normalize_image(encoded('jpg', exif=exif))
        with Image.open(result) as image:
            self.assertEqual(image.size, (24, 32))
            self.assertFalse(image.getexif())
            self.assertNotIn('exif', image.info)

    def test_transparency_and_static_first_frame(self):
        buf = io.BytesIO()
        Image.new('RGBA', (20, 10), (0, 0, 0, 0)).save(buf, 'PNG')
        result = normalize_image(SimpleUploadedFile('alpha.png', buf.getvalue()))
        with Image.open(result) as image:
            self.assertEqual(image.format, 'PNG')
            self.assertEqual(image.getpixel((0, 0))[3], 0)
        buf = io.BytesIO()
        Image.new('RGB', (20, 10), 'red').save(buf, 'GIF', save_all=True,
            append_images=[Image.new('RGB', (20, 10), 'blue')], duration=100, loop=0)
        result = normalize_image(SimpleUploadedFile('animated.gif', buf.getvalue()))
        with Image.open(result) as image:
            self.assertEqual(getattr(image, 'n_frames', 1), 1)
            self.assertGreater(image.convert('RGB').getpixel((0, 0))[0], 240)

    def test_rejects_corruption_active_content_size_and_dimensions(self):
        for name, content in [('fake.jpg', b'MZ executable'), ('bad.png', b'\x89PNG\r\n\x1a\n'),
                              ('active.svg', b'<svg onload="alert(1)"/>'), ('camera.raw', b'raw')]:
            with self.subTest(name=name), self.assertRaises(ValidationError):
                normalize_image(SimpleUploadedFile(name, content))
        oversized = encoded('png')
        oversized.size = 5 * 1024 * 1024 + 1
        with self.assertRaises(ValidationError):
            normalize_image(oversized)
        buf = io.BytesIO()
        Image.new('RGB', (12001, 1)).save(buf, 'PNG')
        with self.assertRaises(ValidationError):
            normalize_image(SimpleUploadedFile('wide.png', buf.getvalue()))
        with patch('apps.core.images.MAX_PIXELS', 100), self.assertRaises(ValidationError):
            normalize_image(encoded('jpg'))

    def test_all_formats_use_private_attachment_normalization(self):
        for ext in FORMATS:
            with self.subTest(extension=ext):
                file, name, kind, mime, size = validate_messaging_attachments([encoded(ext)])[0]
                self.assertEqual(size, file.size)
                self.assertEqual(name, file.name)
                self.assertEqual(kind, 'image')
                self.assertIn(mime, ('image/png', 'image/jpeg'))


class ImageUploadIntegrationTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.temp.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.city = CebuLocation.objects.create(name='Test City', location_type='city', province='Cebu')
        self.shelter = Shelter.objects.create(name='Image Test Shelter', slug='image-test', city=self.city,
            latitude='10.3157', longitude='123.8854',
            is_active=True, is_public=True, verification_status='verified')
        user = get_user_model().objects.create_user(email='images@test.local', password='TestOnly123!',
            full_name='Image Tester', role='platform_admin', is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(user=user)
        self.pet = Pet.objects.create(name='Image Test', shelter=self.shelter, species='dog')

    def test_normalized_multiple_uploads_primary_consistency_and_limit(self):
        url = f'/api/v1/admin-panel/animals/{self.pet.id}/'
        response = self.client.patch(url, {'uploaded_images': [encoded('HEIC'), encoded('TIFF')],
                                         'primary_image_index': 1}, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.pet.images.count(), 2)
        self.assertEqual(self.pet.images.filter(is_primary=True).count(), 1)
        for record in self.pet.images.all():
            with Image.open(record.image_file.path) as image:
                self.assertEqual(image.format, 'JPEG')
        detail = self.client.get(f'/api/v1/pets/{self.pet.id}/').data
        primary = next(item for item in detail['images'] if item['is_primary'])
        self.assertEqual(detail['primary_image'], primary['image_url'])
        self.assertTrue(primary['image_url'].startswith('http://testserver/media/pets/'))
        response = self.client.patch(url, {'uploaded_images': [encoded('png') for _ in range(4)]}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.pet.images.count(), 2)

    def test_bad_batch_leaves_no_files_or_records(self):
        response = self.client.patch(f'/api/v1/admin-panel/animals/{self.pet.id}/',
            {'uploaded_images': [encoded('heif'), SimpleUploadedFile('bad.jpg', b'bad')]}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PetImage.objects.exists())
        self.assertEqual(list(Path(self.temp.name).rglob('*')), [])

    def test_stray_serializer_converts_heif_and_public_capabilities(self):
        from apps.reports.views import StrayReportSerializer
        result = StrayReportSerializer().validate_photo(encoded('HEIF'))
        with Image.open(result) as image:
            self.assertEqual(image.format, 'JPEG')
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v1/core/image-capabilities/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['normalization'], 'raster-v1')
        self.assertEqual(len(response.data['extensions']), 13)

    @override_settings(DEBUG=False)
    def test_public_media_served_in_production_and_blocks_traversal(self):
        response = self.client.patch(
            f'/api/v1/admin-panel/animals/{self.pet.id}/',
            {'uploaded_images': [encoded('jpg')]},
            format='multipart',
        )
        self.assertEqual(response.status_code, 200, response.data)
        detail = self.client.get(f'/api/v1/pets/{self.pet.id}/').data
        media_url = detail['primary_image']
        path = '/' + media_url.split('://', 1)[1].split('/', 1)[1]

        self.client.force_authenticate(user=None)
        img_resp = self.client.get(path)
        self.assertEqual(img_resp.status_code, 200)
        self.assertEqual(img_resp['Content-Type'], 'image/jpeg')
        self.assertEqual(img_resp['Cross-Origin-Resource-Policy'], 'cross-origin')
        self.assertEqual(img_resp['X-Content-Type-Options'], 'nosniff')
        img_resp.close()

        for bad_path in ('/media/../private_media/secret.txt', '/media/../db.sqlite3', '/media/pets/'):
            self.assertEqual(self.client.get(bad_path).status_code, 404)

    def test_shelter_external_image_url_validation(self):
        dynamic_url = 'https://images.example.org/cdn/render?id=12345&size=large#main'
        resp = self.client.post('/api/v1/admin-panel/shelters/', {
            'name': 'External URL Shelter',
            'address': '123 Cebu St',
            'city': self.city.id,
            'latitude': '10.3157000',
            'longitude': '123.8854000',
            'profile_image': dynamic_url,
            'cover_image': 'https://cdn.example.org/cover%20photo.webp?v=2',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data['profile_image'], dynamic_url)
        self.assertEqual(resp.data['cover_image'], 'https://cdn.example.org/cover%20photo.webp?v=2')

        for invalid in ('blob:https://surfur-frontend.vercel.app/123', 'javascript:alert(1)', 'not-a-url'):
            bad_resp = self.client.post('/api/v1/admin-panel/shelters/', {
                'name': f'Bad URL Shelter {invalid[:8]}',
                'address': '123 Cebu St',
                'city': self.city.id,
                'latitude': '10.3157000',
                'longitude': '123.8854000',
                'profile_image': invalid,
            }, format='json')
            self.assertEqual(bad_resp.status_code, 400)
