from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.core.models import CebuLocation
from apps.shelters.models import Shelter
from apps.pets.models import Pet
from apps.adoptions.models import AdoptionInquiry
from rest_framework.test import APIClient
from rest_framework import status
import decimal

User = get_user_model()

class AmponCebuWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # 1. Create Cebu location
        self.location = CebuLocation.objects.create(
            name="Cebu City",
            location_type="city",
            province="Cebu",
            latitude=decimal.Decimal("10.3157"),
            longitude=decimal.Decimal("123.8854"),
            is_active=True,
        )

        # 2. Create users
        self.adopter = User.objects.create_user(
            email="adopter@example.com",
            password="Password123!",
            full_name="Maria Santos",
            role=User.Role.ADOPTER,
        )
        self.shelter_owner = User.objects.create_user(
            email="shelter@example.com",
            password="Password123!",
            full_name="Juan Shelter Admin",
            role=User.Role.SHELTER_ADMIN,
        )
        self.other_shelter_owner = User.objects.create_user(
            email="othershelter@example.com",
            password="Password123!",
            full_name="Pedro Other Admin",
            role=User.Role.SHELTER_ADMIN,
        )

        # 3. Create shelters
        self.shelter = Shelter.objects.create(
            name="Cebu Rescue Hub",
            slug="cebu-rescue-hub",
            organization_type="shelter",
            address="Banilad, Cebu City",
            city=self.location,
            latitude=decimal.Decimal("10.3400"),
            longitude=decimal.Decimal("123.9100"),
            owner=self.shelter_owner,
            verification_status="verified",
            is_active=True,
            is_public=True,
        )
        self.shelter.administrators.add(self.shelter_owner)

        self.other_shelter = Shelter.objects.create(
            name="Mandaue Rescue Hub",
            slug="mandaue-rescue-hub",
            organization_type="shelter",
            address="Subangdaku, Mandaue City",
            city=self.location,
            latitude=decimal.Decimal("10.3280"),
            longitude=decimal.Decimal("123.9350"),
            owner=self.other_shelter_owner,
            verification_status="verified",
            is_active=True,
            is_public=True,
        )
        self.other_shelter.administrators.add(self.other_shelter_owner)

        # 4. Create pet
        self.pet = Pet.objects.create(
            shelter=self.shelter,
            name="Barako",
            species="dog",
            breed="Aspin",
            sex="male",
            size="medium",
            adoption_status="available",
            is_published=True,
            city=self.location,
        )

    def test_anonymous_visitor_can_browse_pets(self):
        """Scenario 1: Visitor can browse pets without logging in."""
        res = self.client.get('/api/v1/pets/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res.data['count'], 1)
        self.assertEqual(res.data['results'][0]['name'], 'Barako')

    def test_pet_filters_return_matching_results(self):
        """Scenario 2: Pet filters return correct matching results."""
        res = self.client.get('/api/v1/pets/?species=cat')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['results']), 0)

        res = self.client.get('/api/v1/pets/?species=dog')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['results']), 1)

    def test_shelter_directory_and_detail(self):
        """Scenarios 3, 4, 5: Public shelter endpoints."""
        res = self.client.get('/api/v1/shelters/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res.data['results']), 1)

        detail_res = self.client.get(f'/api/v1/shelters/{self.shelter.slug}/')
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_res.data['name'], 'Cebu Rescue Hub')

    def test_adopter_registration_and_login(self):
        """Scenario 7: Adopter can register and log in."""
        reg_res = self.client.post('/api/v1/auth/register/', {
            'email': 'newadopter@example.com',
            'full_name': 'New Adopter',
            'password': 'Password123!',
            'password_confirm': 'Password123!',
        })
        self.assertEqual(reg_res.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', reg_res.data)

        login_res = self.client.post('/api/v1/auth/login/', {
            'email': 'newadopter@example.com',
            'password': 'Password123!',
        })
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        self.assertIn('access', login_res.data)

    def test_favorite_toggle(self):
        """Scenario 8: Adopter can save and remove a favorite."""
        self.client.force_authenticate(user=self.adopter)
        fav_res = self.client.post(f'/api/v1/pets/favorites/{self.pet.id}/')
        self.assertEqual(fav_res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(fav_res.data['favorited'])

        # Toggle again to remove
        unfav_res = self.client.post(f'/api/v1/pets/favorites/{self.pet.id}/')
        self.assertEqual(unfav_res.status_code, status.HTTP_200_OK)
        self.assertFalse(unfav_res.data['favorited'])

    def test_adoption_inquiry_workflow(self):
        """Scenarios 9 & 10: Inquiries submission and shelter viewing."""
        self.client.force_authenticate(user=self.adopter)
        inq_res = self.client.post('/api/v1/adoptions/', {
            'pet': str(self.pet.id),
            'applicant_name': 'Maria Santos',
            'applicant_email': 'adopter@example.com',
            'applicant_phone': '09171234567',
            'applicant_city': 'Cebu City',
            'contact_preference': 'email',
            'living_situation': 'house_yard',
            'date_of_birth': '1995-05-15',
            'data_processing_consent': True,
            'responsible_adoption_agreement': True,
        })
        self.assertEqual(inq_res.status_code, status.HTTP_201_CREATED)
        inquiry_id = inq_res.data['id']

        # Shelter owner views inquiries for their own shelter
        self.client.force_authenticate(user=self.shelter_owner)
        shelter_inqs = self.client.get(f'/api/v1/adoptions/shelter/{self.shelter.slug}/')
        self.assertEqual(shelter_inqs.status_code, status.HTTP_200_OK)
        results = shelter_inqs.data.get('results', shelter_inqs.data)
        self.assertEqual(len(results), 1)

        # Update status
        status_res = self.client.patch(f'/api/v1/adoptions/{inquiry_id}/status/', {
            'status': 'under_review',
            'notes': 'Reviewing Maria application',
        })
        self.assertEqual(status_res.status_code, status.HTTP_200_OK)
        self.assertEqual(status_res.data['status'], 'under_review')

    def test_shelter_permission_isolation(self):
        """Scenario 11: A shelter cannot access another shelter's private inquiries."""
        inquiry = AdoptionInquiry.objects.create(
            pet=self.pet,
            shelter=self.shelter,
            applicant=self.adopter,
            applicant_name="Maria Santos",
            applicant_email="adopter@example.com",
            data_processing_consent=True,
            responsible_adoption_agreement=True,
        )

        # Other shelter admin attempts to access or modify status
        self.client.force_authenticate(user=self.other_shelter_owner)
        res = self.client.patch(f'/api/v1/adoptions/{inquiry.id}/status/', {
            'status': 'approved',
        })
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_adopted_pet_excluded_from_available_listings(self):
        """Scenario 15: Adopted animals disappear from the available-pet results."""
        self.pet.adoption_status = 'adopted'
        self.pet.save()

        res = self.client.get('/api/v1/pets/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['results']), 0)
