from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.adoptions.models import AdoptionInquiry
from apps.core.models import AuditLog, CebuLocation
from apps.pets.models import Pet
from apps.shelters.models import Shelter

User = get_user_model()


class CentralizedManagementPermissionsTests(APITestCase):
    def setUp(self):
        self.city = CebuLocation.objects.create(
            name='Cebu City',
            location_type='city',
            province='Cebu',
            latitude='10.3157',
            longitude='123.8854',
        )
        self.platform_admin = User.objects.create_user(
            email='padmin@test.local',
            password='TestPassword!123',
            full_name='Platform Admin',
            role='platform_admin',
            is_staff=True,
        )
        self.shelter1_admin = User.objects.create_user(
            email='s1@test.local',
            password='TestPassword!123',
            full_name='Shelter 1 Admin',
            role='shelter_admin',
        )
        self.shelter2_admin = User.objects.create_user(
            email='s2@test.local',
            password='TestPassword!123',
            full_name='Shelter 2 Admin',
            role='shelter_admin',
        )
        self.adopter = User.objects.create_user(
            email='adopter@test.local',
            password='TestPassword!123',
            full_name='Test Adopter',
            role='adopter',
        )

        self.shelter1 = Shelter.objects.create(
            name='Shelter One',
            slug='shelter-one',
            address='Banilad, Cebu City',
            city=self.city,
            latitude='10.3400',
            longitude='123.9100',
            email='s1org@test.local',
            verification_status='verified',
            is_active=True,
            is_public=True,
        )
        self.shelter1.administrators.add(self.shelter1_admin)

        self.shelter2 = Shelter.objects.create(
            name='Shelter Two',
            slug='shelter-two',
            address='Maribago, Lapu-Lapu',
            city=self.city,
            latitude='10.2880',
            longitude='123.9850',
            email='s2org@test.local',
            verification_status='verified',
            is_active=True,
            is_public=True,
        )
        self.shelter2.administrators.add(self.shelter2_admin)

        self.suspended_shelter = Shelter.objects.create(
            name='Suspended Shelter',
            slug='suspended-shelter',
            address='Mandaue',
            city=self.city,
            latitude='10.3200',
            longitude='123.9300',
            email='susp@test.local',
            verification_status='suspended',
            is_active=True,
            is_public=False,
        )

    def test_platform_admin_can_create_edit_archive_animals_across_shelters_and_cannot_approve_adoptions(self):
        self.client.force_authenticate(user=self.platform_admin)

        # Create animal assigned to Shelter 1
        res1 = self.client.post(
            '/api/v1/admin-panel/animals/',
            {
                'shelter': str(self.shelter1.id),
                'name': 'Bantay',
                'species': 'dog',
                'breed': 'Aspin',
                'sex': 'male',
                'age_category': 'young',
                'size': 'medium',
                'description': 'Friendly rescued dog',
                'is_published': True,
            },
            format='json',
        )
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        pet1_id = res1.data['id']

        # Create animal assigned to Shelter 2
        res2 = self.client.post(
            '/api/v1/admin-panel/animals/',
            {
                'shelter': str(self.shelter2.id),
                'name': 'Muning',
                'species': 'cat',
                'breed': 'Puspin',
                'sex': 'female',
                'age_category': 'adult',
                'size': 'small',
                'description': 'Calm rescued cat',
                'is_published': True,
            },
            format='json',
        )
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)

        # Reject assignment to suspended shelter
        res_susp = self.client.post(
            '/api/v1/admin-panel/animals/',
            {
                'shelter': str(self.suspended_shelter.id),
                'name': 'Blocked',
                'species': 'dog',
                'breed': 'Aspin',
                'sex': 'male',
                'age_category': 'adult',
                'size': 'medium',
                'description': 'Should fail',
            },
            format='json',
        )
        self.assertEqual(res_susp.status_code, status.HTTP_400_BAD_REQUEST)

        # Cannot bypass adoption workflow by directly setting adopted
        res_adopted = self.client.patch(
            f'/api/v1/admin-panel/animals/{pet1_id}/',
            {'adoption_status': 'adopted'},
            format='json',
        )
        self.assertEqual(res_adopted.status_code, status.HTTP_400_BAD_REQUEST)

        # Edit animal details
        res_edit = self.client.patch(
            f'/api/v1/admin-panel/animals/{pet1_id}/',
            {'breed': 'Aspin Mix'},
            format='json',
        )
        self.assertEqual(res_edit.status_code, status.HTTP_200_OK)
        self.assertEqual(res_edit.data['breed'], 'Aspin Mix')

        # Platform Admin CANNOT approve/reject/complete adoption
        inquiry = AdoptionInquiry.objects.create(
            pet_id=pet1_id,
            shelter=self.shelter1,
            applicant=self.adopter,
            applicant_name='Test Adopter',
            applicant_email='adopter@test.local',
            applicant_phone='09171234567',
            applicant_city='Cebu City',
            housing_type='own_house',
            reason_for_adopting='Good home',
        )
        res_approve = self.client.patch(
            f'/api/v1/adoptions/{inquiry.id}/status/',
            {'status': 'approved'},
            format='json',
        )
        self.assertEqual(res_approve.status_code, status.HTTP_403_FORBIDDEN)

        # Archive animal
        res_del = self.client.delete(f'/api/v1/admin-panel/animals/{pet1_id}/')
        self.assertEqual(res_del.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(Pet.objects.get(id=pet1_id).is_archived)

    def test_shelter_admin_is_readonly_for_animals_and_shelter_but_processes_own_adoptions(self):
        pet1 = Pet.objects.create(
            shelter=self.shelter1,
            city=self.city,
            name='Tagpi',
            species='dog',
            breed='Aspin',
            sex='male',
            age_category='young',
            size='medium',
            description='Gentle dog',
            is_published=False,
        )
        pet2 = Pet.objects.create(
            shelter=self.shelter2,
            city=self.city,
            name='PrivateCat',
            species='cat',
            breed='Puspin',
            sex='female',
            age_category='adult',
            size='small',
            description='Unpublished cat in shelter 2',
            is_published=False,
        )
        inquiry1 = AdoptionInquiry.objects.create(
            pet=pet1,
            shelter=self.shelter1,
            applicant=self.adopter,
            applicant_name='Test Adopter',
            applicant_email='adopter@test.local',
            applicant_phone='09171234567',
            applicant_city='Cebu City',
            housing_type='own_house',
            reason_for_adopting='Loving family',
        )
        inquiry2 = AdoptionInquiry.objects.create(
            pet=pet2,
            shelter=self.shelter2,
            applicant=self.adopter,
            applicant_name='Test Adopter',
            applicant_email='adopter@test.local',
            applicant_phone='09171234567',
            applicant_city='Cebu City',
            housing_type='own_house',
            reason_for_adopting='Loving family',
        )

        self.client.force_authenticate(user=self.shelter1_admin)

        # Can view own shelter & own unpublished animal detail
        self.assertEqual(self.client.get('/api/v1/shelters/my-shelter/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(f'/api/v1/pets/{pet1.id}/').status_code, status.HTTP_200_OK)

        # Cannot view other shelter's unpublished animal detail
        self.assertEqual(self.client.get(f'/api/v1/pets/{pet2.id}/').status_code, status.HTTP_404_NOT_FOUND)

        # Cannot edit own shelter
        self.assertEqual(
            self.client.patch('/api/v1/shelters/my-shelter/', {'description': 'Hack'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )

        # Cannot create, edit, or delete animals
        self.assertEqual(
            self.client.post(f'/api/v1/pets/shelter/{self.shelter1.slug}/create/', {'name': 'X'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post('/api/v1/admin-panel/animals/', {'name': 'X'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.patch(f'/api/v1/pets/{pet1.id}/update/', {'name': 'Y'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.delete(f'/api/v1/pets/{pet1.id}/update/').status_code,
            status.HTTP_403_FORBIDDEN,
        )

        # Cannot process Shelter 2's adoption inquiry
        self.assertEqual(
            self.client.patch(f'/api/v1/adoptions/{inquiry2.id}/status/', {'status': 'approved'}, format='json').status_code,
            status.HTTP_404_NOT_FOUND,
        )

        # Can approve and complete Shelter 1's adoption inquiry -> backend marks pet adopted
        r_app = self.client.patch(
            f'/api/v1/adoptions/{inquiry1.id}/status/',
            {'status': 'approved', 'notes': 'Looks great'},
            format='json',
        )
        self.assertEqual(r_app.status_code, status.HTTP_200_OK)
        r_comp = self.client.patch(
            f'/api/v1/adoptions/{inquiry1.id}/status/',
            {'status': 'completed', 'notes': 'Handed over'},
            format='json',
        )
        self.assertEqual(r_comp.status_code, status.HTTP_200_OK)
        pet1.refresh_from_db()
        self.assertEqual(pet1.adoption_status, 'adopted')
        self.assertTrue(AuditLog.objects.filter(action='adoption_completed').exists())

        # Platform Admin cannot reassign pet1 to Shelter 2 when inquiries exist
        self.client.force_authenticate(user=self.platform_admin)
        r_reassign = self.client.patch(
            f'/api/v1/admin-panel/animals/{pet1.id}/',
            {'shelter': str(self.shelter2.id)},
            format='json',
        )
        self.assertEqual(r_reassign.status_code, status.HTTP_400_BAD_REQUEST)
