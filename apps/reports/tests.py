import io
import os
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.models import CebuLocation
from apps.notifications.models import Notification
from apps.reports.models import StrayReport, StrayReportStatusHistory
from apps.shelters.models import Shelter

User = get_user_model()


def make_test_png(name='test.png'):
    buf = io.BytesIO()
    img = Image.new('RGB', (32, 32), color=(244, 67, 90))
    img.save(buf, format='PNG')
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type='image/png')


class StrayReportAndAnalyticsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.city = CebuLocation.objects.create(
            name='Cebu City',
            location_type='city',
            province='Cebu',
            is_active=True,
            latitude=10.3157,
            longitude=123.8854,
        )
        self.adopter1 = User.objects.create_user(
            email='adopter1@surfur.test',
            password='Password123!',
            full_name='Adopter One',
            role=User.Role.ADOPTER,
        )
        self.adopter2 = User.objects.create_user(
            email='adopter2@surfur.test',
            password='Password123!',
            full_name='Adopter Two',
            role=User.Role.ADOPTER,
        )
        self.platform_admin = User.objects.create_user(
            email='padmin@surfur.test',
            password='Password123!',
            full_name='Platform Admin',
            role=User.Role.PLATFORM_ADMIN,
        )
        self.shelter_admin1 = User.objects.create_user(
            email='sadmin1@surfur.test',
            password='Password123!',
            full_name='Shelter Admin 1',
            role=User.Role.SHELTER_ADMIN,
        )
        self.shelter_admin2 = User.objects.create_user(
            email='sadmin2@surfur.test',
            password='Password123!',
            full_name='Shelter Admin 2',
            role=User.Role.SHELTER_ADMIN,
        )
        self.shelter1 = Shelter.objects.create(
            name='Rescue One',
            slug='rescue-one',
            address='Lahug, Cebu City',
            city=self.city,
            latitude=10.3157,
            longitude=123.8854,
            verification_status=Shelter.VerificationStatus.VERIFIED,
            owner=self.shelter_admin1,
        )
        self.shelter1.administrators.add(self.shelter_admin1)
        self.shelter2 = Shelter.objects.create(
            name='Rescue Two',
            slug='rescue-two',
            address='Mandaue City',
            city=self.city,
            latitude=10.32,
            longitude=123.90,
            verification_status=Shelter.VerificationStatus.VERIFIED,
            owner=self.shelter_admin2,
        )
        self.shelter2.administrators.add(self.shelter_admin2)

    def test_hybrid_guest_reporting_tracking_and_admins_blocked(self):
        payload = {
            'animal_type': 'dog',
            'animal_description': 'Brown aspin near park',
            'city': self.city.id,
            'location_description': 'Fuente Osmena',
            'sighted_at': timezone.now().isoformat(),
            'urgency': 'medium',
            'reporter_name': 'Guest Rescuer',
            'reporter_email': 'guest@gmail.com',
            'reporter_phone': '09171234567',
            'data_processing_consent': True,
        }
        # Admins remain blocked from public reporting
        self.client.force_authenticate(user=self.platform_admin)
        self.assertEqual(self.client.post('/api/v1/reports/', payload, format='json').status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(user=self.shelter_admin1)
        self.assertEqual(self.client.post('/api/v1/reports/', payload, format='json').status_code, status.HTTP_403_FORBIDDEN)

        # Unauthenticated guest can submit
        self.client.force_authenticate(user=None)
        res = self.client.post('/api/v1/reports/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['reporter_type'], 'guest')
        self.assertFalse(res.data['contact_verified'])
        self.assertTrue(res.data['tracking_token'])

        # Rapid duplicate cooldown
        dup_res = self.client.post('/api/v1/reports/', payload, format='json')
        self.assertEqual(dup_res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        # Secure tracking rejects wrong token and accepts valid token without exposing PII
        ref = res.data['report_number']
        tok = res.data['tracking_token']
        self.assertEqual(
            self.client.post('/api/v1/reports/track/', {'report_number': ref, 'tracking_token': 'wrong-token'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        track_ok = self.client.post('/api/v1/reports/track/', {'report_number': ref, 'tracking_token': tok}, format='json')
        self.assertEqual(track_ok.status_code, status.HTTP_200_OK)
        self.assertNotIn('reporter_email', track_ok.data)
        self.assertNotIn('reporter_phone', track_ok.data)
        self.assertNotIn('resolution_notes', track_ok.data)

    def test_phone_and_email_validation(self):
        self.client.force_authenticate(user=self.adopter1)
        base = {
            'animal_type': 'cat',
            'animal_description': 'White kitten',
            'city': self.city.id,
            'location_description': 'IT Park',
            'sighted_at': timezone.now().isoformat(),
            'urgency': 'high',
            'reporter_name': 'Adopter One',
            'reporter_email': 'adopter1@gmail.com',
            'reporter_phone': '09171234567',
            'data_processing_consent': True,
        }
        for bad_phone in ['09661234', '096612348891', '12345678901', '09abcdefgh1']:
            p = dict(base, reporter_phone=bad_phone)
            res = self.client.post('/api/v1/reports/', p, format='json')
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('reporter_phone', res.data)

        for bad_email in ['reporter', 'reporter@gmail', 'reporter@', '@gmail.com', 'reporter gmail.com']:
            p = dict(base, reporter_email=bad_email)
            res = self.client.post('/api/v1/reports/', p, format='json')
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('reporter_email', res.data)

    def test_full_stray_report_upload_tracking_and_rescue_notifications(self):
        self.client.force_authenticate(user=self.adopter1)
        photo = make_test_png('stray_dog.png')
        res = self.client.post(
            '/api/v1/reports/',
            {
                'animal_type': 'dog',
                'animal_description': 'Limping brown aspin',
                'city': self.city.id,
                'location_description': 'Ayala Center Cebu',
                'sighted_at': timezone.now().isoformat(),
                'urgency': 'high',
                'reporter_name': 'Adopter One',
                'reporter_email': 'adopter1@gmail.com',
                'reporter_phone': '09661234889',
                'data_processing_consent': 'true',
                'photo': photo,
            },
            format='multipart',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        report_id = res.data['id']
        self.assertTrue(res.data['photo_url'])

        report = StrayReport.objects.get(id=report_id)
        self.assertEqual(report.reporter, self.adopter1)
        self.assertTrue(os.path.exists(report.photo.path))

        # Adopter2 cannot view Adopter1's private report
        self.client.force_authenticate(user=self.adopter2)
        self.assertEqual(self.client.get(f'/api/v1/reports/mine/{report_id}/').status_code, status.HTTP_404_NOT_FOUND)

        # Platform Admin sees photo_url, assigns to shelter1
        self.client.force_authenticate(user=self.platform_admin)
        admin_list = self.client.get('/api/v1/admin-panel/stray-reports/').data['results']
        self.assertTrue(any(r['id'] == report_id and r['photo_url'] for r in admin_list))

        assign_res = self.client.patch(
            f'/api/v1/admin-panel/stray-reports/{report_id}/',
            {'status': 'assigned', 'assigned_organization': str(self.shelter1.id), 'public_note': 'Dispatched to Rescue One.'},
            format='json',
        )
        self.assertEqual(assign_res.status_code, status.HTTP_200_OK)

        # Shelter2 cannot update Shelter1's assigned report
        self.client.force_authenticate(user=self.shelter_admin2)
        self.assertEqual(
            self.client.patch(f'/api/v1/reports/shelter-assigned/{report_id}/', {'status': 'rescued'}, format='json').status_code,
            status.HTTP_404_NOT_FOUND,
        )

        # Shelter1 marks rescued
        self.client.force_authenticate(user=self.shelter_admin1)
        rescue_res = self.client.patch(
            f'/api/v1/reports/shelter-assigned/{report_id}/',
            {'status': 'rescued', 'public_note': 'Safely rescued and resting at shelter.'},
            format='json',
        )
        self.assertEqual(rescue_res.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(rescue_res.data['rescued_at'])

        # Adopter1 receives rescue notification and sees timeline
        self.assertTrue(
            Notification.objects.filter(
                user=self.adopter1,
                related_resource_type='stray_report',
                related_resource_id=str(report_id),
                title='Stray Animal Successfully Rescued!',
            ).exists()
        )
        self.assertEqual(StrayReportStatusHistory.objects.filter(report=report).count(), 3)

        # Clean up uploaded test file
        if report.photo and os.path.exists(report.photo.path):
            os.remove(report.photo.path)

    def test_shelter_animal_image_upload_and_admin_reports_analytics(self):
        # Shelter Admin cannot upload/create animals; Platform Admin creates & uploads animal photos
        self.client.force_authenticate(user=self.shelter_admin1)
        blocked_res = self.client.post(
            f'/api/v1/pets/shelter/{self.shelter1.slug}/create/',
            {'name': 'Choco', 'species': 'dog'},
            format='multipart',
        )
        self.assertEqual(blocked_res.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.platform_admin)
        pet_res = self.client.post(
            f'/api/v1/pets/shelter/{self.shelter1.slug}/create/',
            {
                'name': 'Choco',
                'species': 'dog',
                'adoption_status': 'available',
                'is_published': 'true',
                'uploaded_image': make_test_png('choco.png'),
            },
            format='multipart',
        )
        self.assertEqual(pet_res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(pet_res.data['images'][0]['image_url'])

        # Platform Admin Reports & CSV export
        self.client.force_authenticate(user=self.platform_admin)
        rep_res = self.client.get('/api/v1/admin-panel/reports/')
        self.assertEqual(rep_res.status_code, status.HTTP_200_OK)
        self.assertIn('stray_reports', rep_res.data)
        self.assertIn('shelter_comparison', rep_res.data)

        csv_res = self.client.get('/api/v1/admin-panel/reports/export/')
        self.assertEqual(csv_res.status_code, status.HTTP_200_OK)
        self.assertEqual(csv_res['Content-Type'], 'text/csv')
        self.assertIn(b'Category,Metric,Count', csv_res.content)
