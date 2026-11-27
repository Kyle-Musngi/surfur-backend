import io
import os
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase
from apps.core.models import AuditLog, CebuLocation
from apps.notifications.models import Notification
from apps.pets.models import Pet
from apps.shelters.models import Shelter

User = get_user_model()


def make_test_png(name='photo.png'):
    buf = io.BytesIO()
    Image.new('RGB', (16, 16), color=(120, 200, 140)).save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


def make_test_pdf(name='doc.pdf'):
    return SimpleUploadedFile(name, b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF', content_type='application/pdf')


class MessagingSystemTests(APITestCase):
    def setUp(self):
        self.city = CebuLocation.objects.create(
            name='Cebu City',
            location_type='city',
            province='Cebu',
            latitude='10.3157',
            longitude='123.8854',
        )
        self.platform_admin = User.objects.create_user(
            email='padmin@msg.test',
            password='TestPassword!123',
            full_name='SurFur Administrator',
            role='platform_admin',
            is_staff=True,
        )
        self.shelter1_admin = User.objects.create_user(
            email='s1@msg.test',
            password='TestPassword!123',
            full_name='Shelter One Staff',
            role='shelter_admin',
        )
        self.shelter2_admin = User.objects.create_user(
            email='s2@msg.test',
            password='TestPassword!123',
            full_name='Shelter Two Staff',
            role='shelter_admin',
        )
        self.adopter = User.objects.create_user(
            email='adopter@msg.test',
            password='TestPassword!123',
            full_name='Adopter User',
            role='adopter',
        )
        self.shelter1 = Shelter.objects.create(
            name='Island Paws Cebu',
            slug='island-paws-cebu',
            address='Banilad, Cebu City',
            city=self.city,
            latitude='10.3400',
            longitude='123.9100',
            email='s1@org.test',
            verification_status='verified',
            is_active=True,
            is_public=True,
        )
        self.shelter1.administrators.add(self.shelter1_admin)

        self.shelter2 = Shelter.objects.create(
            name='Lapu-Lapu Coastal Rescue',
            slug='lapu-lapu-coastal-rescue',
            address='Maribago, Lapu-Lapu',
            city=self.city,
            latitude='10.2880',
            longitude='123.9850',
            email='s2@org.test',
            verification_status='verified',
            is_active=True,
            is_public=True,
        )
        self.shelter2.administrators.add(self.shelter2_admin)

        self.pet1 = Pet.objects.create(
            shelter=self.shelter1,
            city=self.city,
            name='Bantay',
            species='dog',
            breed='Aspin',
            sex='male',
            age_category='young',
            size='medium',
            description='Friendly dog',
        )

    def test_adopter_and_guest_blocked_from_messaging(self):
        self.assertEqual(self.client.get('/api/v1/messaging/conversations/').status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(user=self.adopter)
        self.assertEqual(self.client.get('/api/v1/messaging/conversations/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/v1/messaging/unread-count/').status_code, status.HTTP_403_FORBIDDEN)

    def test_two_way_messaging_quick_requests_attachments_read_receipts_and_cross_shelter_isolation(self):
        # Shelter 1 gets/creates conversation and sends Request to Add an Animal with PNG attachment
        self.client.force_authenticate(user=self.shelter1_admin)
        c_res = self.client.get('/api/v1/messaging/conversations/')
        self.assertEqual(c_res.status_code, status.HTTP_200_OK)
        conv1_id = c_res.data['results'][0]['id']

        m_res = self.client.post(
            f'/api/v1/messaging/conversations/{conv1_id}/messages/',
            {
                'content': 'Request to Add an Animal: Bantay Jr.',
                'request_type': 'add_animal',
                'client_id': 'req-123',
                'attachments': [make_test_png('bantay.png'), make_test_pdf('vax.pdf')],
            },
            format='multipart',
        )
        self.assertEqual(m_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(m_res.data['attachments']), 2)
        att_id = m_res.data['attachments'][0]['id']
        self.assertFalse(m_res.data['is_read'])

        # Duplicate client_id returns existing message without creating duplicate
        dup_res = self.client.post(
            f'/api/v1/messaging/conversations/{conv1_id}/messages/',
            {'content': 'Request to Add an Animal: Bantay Jr.', 'client_id': 'req-123'},
            format='multipart',
        )
        self.assertEqual(dup_res.status_code, status.HTTP_200_OK)
        self.assertEqual(dup_res.data['id'], m_res.data['id'])

        # Unsupported file type is rejected
        bad_file = SimpleUploadedFile('malware.exe', b'MZ...', content_type='application/octet-stream')
        bad_res = self.client.post(
            f'/api/v1/messaging/conversations/{conv1_id}/messages/',
            {'content': 'Bad file', 'attachments': [bad_file]},
            format='multipart',
        )
        self.assertEqual(bad_res.status_code, status.HTTP_400_BAD_REQUEST)

        # Shelter 2 CANNOT view Shelter 1 conversation, messages, or attachment
        self.client.force_authenticate(user=self.shelter2_admin)
        self.assertEqual(
            self.client.get(f'/api/v1/messaging/conversations/{conv1_id}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(f'/api/v1/messaging/conversations/{conv1_id}/messages/').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(f'/api/v1/messaging/attachments/{att_id}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )

        # Platform Admin sees unread count = 1, marks read, downloads attachment, and replies
        self.client.force_authenticate(user=self.platform_admin)
        unread_res = self.client.get('/api/v1/messaging/unread-count/')
        self.assertEqual(unread_res.data['unread_count'], 1)
        self.assertEqual(
            self.client.get(f'/api/v1/messaging/attachments/{att_id}/').status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(f'/api/v1/messaging/conversations/{conv1_id}/mark-read/').status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(self.client.get('/api/v1/messaging/unread-count/').data['unread_count'], 0)

        reply_res = self.client.post(
            f'/api/v1/messaging/conversations/{conv1_id}/messages/',
            {'content': 'Received! I will add this animal listing shortly.'},
            format='json',
        )
        self.assertEqual(reply_res.status_code, status.HTTP_201_CREATED)

        # Shelter 1 sees read receipt on their original message and unread reply notification
        self.client.force_authenticate(user=self.shelter1_admin)
        self.assertEqual(self.client.get('/api/v1/messaging/unread-count/').data['unread_count'], 1)
        msgs = self.client.get(f'/api/v1/messaging/conversations/{conv1_id}/messages/').data['results']
        self.assertTrue(msgs[0]['is_read'])
        self.assertTrue(Notification.objects.filter(user=self.shelter1_admin, related_resource_type='conversation').exists())
        self.assertTrue(AuditLog.objects.filter(action='animal_add_requested').exists())
        self.assertTrue(AuditLog.objects.filter(action='admin_replied_shelter').exists())
