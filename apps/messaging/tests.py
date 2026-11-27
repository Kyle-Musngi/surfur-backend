import io
import os
import tempfile
from pypdf import PdfWriter
from unittest.mock import patch
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase
from apps.core.models import AuditLog, CebuLocation
from apps.notifications.models import Notification
from apps.pets.models import Pet
from apps.shelters.models import Shelter
from .models import Message, MessageReadState, private_messaging_storage

User = get_user_model()


def make_test_png(name='photo.png'):
    buf = io.BytesIO()
    Image.new('RGB', (16, 16), color=(120, 200, 140)).save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


def make_test_pdf(name='doc.pdf'):
    buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(buf)
    return SimpleUploadedFile(name, buf.getvalue(), content_type='application/pdf')


class MessagingSystemTests(APITestCase):
    def setUp(self):
        temporary_media = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_media.cleanup)
        storage_patch = patch.object(private_messaging_storage, 'location', temporary_media.name)
        storage_patch.start()
        self.addCleanup(storage_patch.stop)
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
        download = self.client.get(f'/api/v1/messaging/attachments/{att_id}/')
        self.assertEqual(download.status_code, status.HTTP_200_OK)
        download.close()
        self.assertEqual(
            self.client.post(f'/api/v1/messaging/conversations/{conv1_id}/mark-read/', {'last_read_message': m_res.data['id']}).status_code,
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

    def conversation(self):
        self.client.force_authenticate(user=self.shelter1_admin)
        return self.client.post('/api/v1/messaging/conversations/').data['id']

    def test_read_watermark_does_not_mark_unseen_messages_or_move_backward(self):
        conv = self.conversation()
        url = f'/api/v1/messaging/conversations/{conv}/messages/'
        first = self.client.post(url, {'content': 'First'}).data
        second = self.client.post(url, {'content': 'Second'}).data
        self.client.force_authenticate(user=self.platform_admin)
        mark = f'/api/v1/messaging/conversations/{conv}/mark-read/'
        self.assertEqual(self.client.post(mark, {'last_read_message': first['id']}).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/messaging/unread-count/').data['unread_count'], 1)
        self.client.post(mark, {'last_read_message': second['id']})
        self.client.post(mark, {'last_read_message': first['id']})
        self.assertEqual(self.client.get('/api/v1/messaging/unread-count/').data['unread_count'], 0)

    def test_sending_does_not_mark_incoming_messages_read(self):
        conv = self.conversation()
        url = f'/api/v1/messaging/conversations/{conv}/messages/'
        self.client.post(url, {'content': 'Unread request'})
        self.client.force_authenticate(user=self.platform_admin)
        self.client.post(url, {'content': 'Reply'})
        self.assertEqual(self.client.get('/api/v1/messaging/unread-count/').data['unread_count'], 1)

    def test_malformed_ids_dates_and_foreign_references(self):
        conv = self.conversation()
        url = f'/api/v1/messaging/conversations/{conv}/messages/'
        self.assertEqual(self.client.get(url, {'since': 'invalid'}).status_code, 400)
        self.assertEqual(self.client.get(url, {'before': 'invalid'}).status_code, 400)
        self.assertEqual(self.client.post(url, {'content': 'x', 'related_pet': 'invalid'}).status_code, 400)
        self.client.force_authenticate(user=self.platform_admin)
        self.assertEqual(self.client.post('/api/v1/messaging/conversations/', {'shelter_id': 'invalid'}).status_code, 400)
        self.client.force_authenticate(user=self.shelter2_admin)
        other = self.client.post('/api/v1/messaging/conversations/').data['id']
        self.assertEqual(self.client.post(f'/api/v1/messaging/conversations/{other}/messages/', {'content': 'x', 'related_pet': str(self.pet1.id)}).status_code, 400)
        self.assertEqual(self.client.post(url, {'content': 'x'}).status_code, 404)
        self.assertEqual(self.client.post(f'/api/v1/messaging/conversations/{conv}/mark-read/', {'last_read_message': str(self.pet1.id)}).status_code, 404)

    def test_all_request_types_preserve_official_records_and_sender(self):
        conv = self.conversation()
        counts = (Pet.objects.count(), Shelter.objects.count())
        for kind, _ in Message.RequestType.choices:
            response = self.client.post(f'/api/v1/messaging/conversations/{conv}/messages/', {
                'content': 'Demonstration request', 'request_type': kind,
                'related_pet': str(self.pet1.id), 'sender': str(self.platform_admin.id),
                'request_metadata': {'shelter_id': str(self.shelter2.id)},
            }, format='json')
            self.assertEqual(response.status_code, 201)
            self.assertEqual(str(response.data['sender']), str(self.shelter1_admin.id))
            self.assertEqual(response.data['request_metadata']['shelter_id'], str(self.shelter1.id))
        self.assertEqual(counts, (Pet.objects.count(), Shelter.objects.count()))
        self.pet1.refresh_from_db()
        self.assertEqual(self.pet1.name, 'Bantay')

    def test_active_and_fake_pdf_rejected_and_image_mime_derived(self):
        conv = self.conversation()
        url = f'/api/v1/messaging/conversations/{conv}/messages/'
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        from pypdf.generic import DictionaryObject, NameObject, TextStringObject
        writer.root_object[NameObject('/OpenAction')] = DictionaryObject({
            NameObject('/S'): NameObject('/JavaScript'), NameObject('/JS'): TextStringObject('app.alert(1)'),
        })
        buf = io.BytesIO()
        writer.write(buf)
        for data in (buf.getvalue(), b'%PDF-fake executable'):
            result = self.client.post(url, {'content': 'x', 'attachments': [SimpleUploadedFile('test.pdf', data)]}, format='multipart')
            self.assertEqual(result.status_code, 400)
        picture = make_test_png()
        picture.content_type = 'text/html'
        result = self.client.post(url, {'content': 'x', 'attachments': [picture]}, format='multipart')
        self.assertEqual(result.status_code, 201)
        attachment = result.data['attachments'][0]
        response = self.client.get(f"/api/v1/messaging/attachments/{attachment['id']}/")
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        response.close()
        self.client.force_authenticate(user=self.adopter)
        self.assertEqual(self.client.get(f"/api/v1/messaging/attachments/{attachment['id']}/").status_code, 403)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(f"/api/v1/messaging/attachments/{attachment['id']}/").status_code, 401)

    def test_history_and_receipt_refresh_without_new_messages(self):
        conv = self.conversation()
        for number in range(45):
            Message.objects.create(conversation_id=conv, sender=self.shelter1_admin, content=f'Test {number}')
        url = f'/api/v1/messaging/conversations/{conv}/messages/'
        latest = self.client.get(url).data
        self.assertEqual(len(latest['results']), 40)
        older = self.client.get(url, {'before': latest['results'][0]['created_at'], 'before_id': latest['results'][0]['id']}).data
        self.assertEqual(len(older['results']), 5)
        last = latest['results'][-1]
        self.client.force_authenticate(user=self.platform_admin)
        self.client.post(f'/api/v1/messaging/conversations/{conv}/mark-read/', {'last_read_message': last['id']})
        self.client.force_authenticate(user=self.shelter1_admin)
        response = self.client.get(url, {'since': last['created_at']}).data
        self.assertEqual(response['results'], [])
        self.assertIsNotNone(response['recipient_read_at'])
