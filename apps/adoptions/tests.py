import datetime
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from apps.core.models import CebuLocation
from apps.shelters.models import Shelter
from apps.pets.models import Pet
from apps.adoptions.models import AdoptionInquiry

User = get_user_model()


class SurFurAdoptionFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create service location
        self.location = CebuLocation.objects.create(
            name='Cebu City',
            location_type='city',
            province='Cebu',
            is_active=True,
            latitude=10.3157,
            longitude=123.8854,
        )

        # Create shelter admin user
        self.shelter_admin = User.objects.create_user(
            email='shelteradmin@surfur.test',
            password='Password123!',
            full_name='Shelter Coordinator',
            role=User.Role.SHELTER_ADMIN,
        )

        # Create shelter
        self.shelter = Shelter.objects.create(
            name='Happy Paws Rescue Cebu',
            slug='happy-paws-rescue',
            city=self.location,
            latitude=10.3157,
            longitude=123.8854,
            owner=self.shelter_admin,
            verification_status='verified',
            is_active=True,
            is_public=True,
        )
        self.shelter.administrators.add(self.shelter_admin)

        # Create another shelter for exclusivity testing
        self.other_shelter = Shelter.objects.create(
            name='Island Fur Sanctuary',
            slug='island-fur-sanctuary',
            city=self.location,
            latitude=10.3200,
            longitude=123.8900,
            verification_status='verified',
            is_active=True,
            is_public=True,
        )

        # Create pets
        self.pet1 = Pet.objects.create(
            shelter=self.shelter,
            name='Bantay',
            species='dog',
            breed='Aspin',
            sex='male',
            size='medium',
            age_years=2,
            adoption_status='available',
            is_published=True,
        )

        self.other_pet = Pet.objects.create(
            shelter=self.other_shelter,
            name='Muning',
            species='cat',
            breed='Puspin',
            sex='female',
            size='small',
            age_years=1,
            adoption_status='available',
            is_published=True,
        )

    def test_under_18_adoption_application_strictly_rejected(self):
        """Under-18 applicant must be rejected with HTTP 400."""
        # Calculate DOB for 16-year-old
        sixteen_years_ago = datetime.date.today() - datetime.timedelta(days=16 * 365.25)
        payload = {
            'pet': str(self.pet1.id),
            'applicant_name': 'Minor Applicant',
            'applicant_email': 'minor@example.com',
            'applicant_phone': '09123456789',
            'applicant_city': 'Cebu City',
            'date_of_birth': sixteen_years_ago.strftime('%Y-%m-%d'),
            'housing_type': 'homeowner',
            'data_processing_consent': True,
            'responsible_adoption_agreement': True,
        }

        response = self.client.post('/api/v1/adoptions/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('date_of_birth', response.data)
        self.assertTrue(
            any('18' in str(msg) for msg in response.data['date_of_birth'])
        )

    def test_18_plus_adoption_application_succeeds_with_reference_number(self):
        """Adult applicant (>=18) succeeds and receives unique reference number."""
        twenty_years_ago = datetime.date.today() - datetime.timedelta(days=20 * 365.25)
        payload = {
            'pet': str(self.pet1.id),
            'applicant_name': 'Adult Applicant',
            'applicant_email': 'adult@example.com',
            'applicant_phone': '09123456789',
            'applicant_city': 'Cebu City',
            'date_of_birth': twenty_years_ago.strftime('%Y-%m-%d'),
            'housing_type': 'homeowner',
            'data_processing_consent': True,
            'responsible_adoption_agreement': True,
        }

        response = self.client.post('/api/v1/adoptions/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('reference_number', response.data)
        self.assertTrue(response.data['reference_number'].startswith('APP-'))

        # Check DB persistence
        inquiry = AdoptionInquiry.objects.get(id=response.data['id'])
        self.assertEqual(inquiry.status, 'submitted')
        self.assertEqual(inquiry.shelter, self.shelter)

    def test_shelter_pet_listing_exclusivity(self):
        """Shelter profile pet listing endpoint only returns pets belonging exclusively to that shelter."""
        response = self.client.get(f'/api/v1/pets/shelter/{self.shelter.slug}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data['results'] if 'results' in response.data else response.data
        pet_ids = [str(p['id']) for p in results]
        self.assertIn(str(self.pet1.id), pet_ids)
        self.assertNotIn(str(self.other_pet.id), pet_ids)

    def test_shelter_admin_can_update_application_status_and_finalize_pet(self):
        """Shelter coordinator updates application status to approved/completed and pet syncs."""
        # Create application
        twenty_years_ago = datetime.date.today() - datetime.timedelta(days=25 * 365.25)
        inquiry = AdoptionInquiry.objects.create(
            pet=self.pet1,
            shelter=self.shelter,
            applicant_name='Jane Doe',
            applicant_email='jane@example.com',
            date_of_birth=twenty_years_ago,
            housing_type='homeowner',
            status='submitted',
            data_processing_consent=True,
            responsible_adoption_agreement=True,
        )

        # Authenticate as shelter coordinator
        self.client.force_authenticate(user=self.shelter_admin)

        # Update status to completed / finalize adoption
        response = self.client.patch(
            f'/api/v1/adoptions/{inquiry.id}/status/',
            {'status': 'completed', 'notes': 'Adoption covenant finalized.'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Reload objects
        inquiry.refresh_from_db()
        self.pet1.refresh_from_db()

        self.assertEqual(inquiry.status, 'completed')
        self.assertEqual(self.pet1.adoption_status, 'adopted')
        self.assertEqual(inquiry.status_history.count(), 1)
