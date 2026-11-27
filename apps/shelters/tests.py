from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from apps.core.models import CebuLocation
from apps.shelters.models import Shelter, ShelterVerification

User = get_user_model()


class ShelterRegistrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.location = CebuLocation.objects.create(
            name='Cebu City',
            location_type='city',
            province='Cebu',
            is_active=True,
            latitude=10.3157,
            longitude=123.8854,
        )

        self.inactive_location = CebuLocation.objects.create(
            name='Inactive Municipality',
            location_type='municipality',
            province='Cebu',
            is_active=False,
            latitude=10.0000,
            longitude=123.0000,
        )

        self.adopter = User.objects.create_user(
            email='rescuer@surfur.test',
            password='Password123!',
            full_name='Maria Santos',
            role=User.Role.ADOPTER,
        )

        self.shelter_admin = User.objects.create_user(
            email='shelterowner@surfur.test',
            password='Password123!',
            full_name='Juan Dela Cruz',
            role=User.Role.SHELTER_ADMIN,
        )

        self.platform_admin = User.objects.create_user(
            email='admin@surfur.test',
            password='Password123!',
            full_name='Platform Owner',
            role=User.Role.PLATFORM_ADMIN,
        )

        self.valid_payload = {
            'name': 'Cebu Hope Paws Haven',
            'organization_type': 'rescue_org',
            'description': 'A sanctuary dedicated to rescued dogs and cats.',
            'mission': 'Rehabilitate strays and find forever homes across Cebu.',
            'address': 'Barangay Lahug, Cebu City',
            'city': self.location.id,
            'phone_number': '+63 917 123 4567',
            'email': 'contact@cebuhopepaws.org',
            'animal_types': 'both',
            'contact_person': 'Maria Santos',
            'postal_code': '6000',
            'province': 'Cebu',
            'verification_document_url': 'https://drive.google.com/file/d/sec-cert',
            'verification_notes': 'SEC Registered Animal Welfare NGO',
            'confirmation_accurate': True,
            'privacy_consent': True,
        }

    def test_unauthenticated_registration_rejected(self):
        response = self.client.post('/api/v1/shelters/register/', self.valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_adopter_and_shelter_admin_cannot_register_shelter(self):
        self.client.force_authenticate(user=self.adopter)
        res_adopter = self.client.post('/api/v1/shelters/register/', self.valid_payload, format='json')
        self.assertEqual(res_adopter.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.shelter_admin)
        res_shelter = self.client.post('/api/v1/shelters/register/', self.valid_payload, format='json')
        self.assertEqual(res_shelter.status_code, status.HTTP_403_FORBIDDEN)

    def test_platform_admin_shelter_registration_success(self):
        self.client.force_authenticate(user=self.platform_admin)
        response = self.client.post('/api/v1/shelters/register/', self.valid_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data

        shelter = Shelter.objects.get(id=data['id'])
        self.assertEqual(shelter.name, 'Cebu Hope Paws Haven')
        self.assertEqual(shelter.verification_status, Shelter.VerificationStatus.PENDING)
        self.assertAlmostEqual(float(shelter.latitude), 10.3157, places=4)
        self.assertAlmostEqual(float(shelter.longitude), 123.8854, places=4)

        verifications = ShelterVerification.objects.filter(shelter=shelter)
        self.assertEqual(verifications.count(), 1)
        self.assertEqual(verifications.first().review_status, ShelterVerification.ReviewStatus.PENDING)

    def test_duplicate_shelter_name_rejected(self):
        self.client.force_authenticate(user=self.platform_admin)
        self.client.post('/api/v1/shelters/register/', self.valid_payload, format='json')

        duplicate_payload = self.valid_payload.copy()
        duplicate_payload['name'] = 'CEBU HOPE PAWS HAVEN'
        response = self.client.post('/api/v1/shelters/register/', duplicate_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', response.data)

    def test_legal_consent_required(self):
        self.client.force_authenticate(user=self.platform_admin)

        payload_no_acc = self.valid_payload.copy()
        payload_no_acc['confirmation_accurate'] = False
        res1 = self.client.post('/api/v1/shelters/register/', payload_no_acc, format='json')
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('confirmation_accurate', res1.data)

        payload_no_priv = self.valid_payload.copy()
        payload_no_priv['privacy_consent'] = False
        res2 = self.client.post('/api/v1/shelters/register/', payload_no_priv, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('privacy_consent', res2.data)

    def test_inactive_location_rejected(self):
        self.client.force_authenticate(user=self.platform_admin)
        invalid_payload = self.valid_payload.copy()
        invalid_payload['city'] = self.inactive_location.id

        response = self.client.post('/api/v1/shelters/register/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('city', response.data)
