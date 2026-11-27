from io import StringIO
from django.core.management import call_command
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient
from apps.core.models import AuditLog, CebuLocation
from apps.shelters.models import Shelter
from apps.pets.models import Pet
from apps.adoptions.models import AdoptionInquiry

User = get_user_model()


class RoleBasedSecurityTests(TestCase):
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
        self.platform_admin = User.objects.create_user(
            email='padmin@surfur.test',
            password='StrongPassword123!',
            full_name='Platform Admin',
            role=User.Role.PLATFORM_ADMIN,
        )
        self.shelter_admin_a = User.objects.create_user(
            email='sheltera@surfur.test',
            password='StrongPassword123!',
            full_name='Shelter Admin A',
            role=User.Role.SHELTER_ADMIN,
        )
        self.shelter_admin_b = User.objects.create_user(
            email='shelterb@surfur.test',
            password='StrongPassword123!',
            full_name='Shelter Admin B',
            role=User.Role.SHELTER_ADMIN,
        )
        self.adopter = User.objects.create_user(
            email='adopter@surfur.test',
            password='StrongPassword123!',
            full_name='Regular Adopter',
            role=User.Role.ADOPTER,
        )

        self.shelter_a = Shelter.objects.create(
            name='Shelter A',
            slug='shelter-a',
            address='Lahug, Cebu City',
            city=self.city,
            latitude=10.3157,
            longitude=123.8854,
            verification_status=Shelter.VerificationStatus.VERIFIED,
            is_active=True,
            is_public=True,
            owner=self.shelter_admin_a,
        )
        self.shelter_a.administrators.add(self.shelter_admin_a)

        self.shelter_b = Shelter.objects.create(
            name='Shelter B',
            slug='shelter-b',
            address='Mandaue City',
            city=self.city,
            latitude=10.3200,
            longitude=123.9000,
            verification_status=Shelter.VerificationStatus.VERIFIED,
            is_active=True,
            is_public=True,
            owner=self.shelter_admin_b,
        )
        self.shelter_b.administrators.add(self.shelter_admin_b)

        self.pet_a = Pet.objects.create(
            shelter=self.shelter_a,
            name='Bantay',
            species=Pet.Species.DOG,
            adoption_status=Pet.AdoptionStatus.AVAILABLE,
            is_published=True,
            city=self.city,
        )

        self.inquiry_a = AdoptionInquiry.objects.create(
            applicant=self.adopter,
            pet=self.pet_a,
            shelter=self.shelter_a,
            applicant_name='Regular Adopter',
            applicant_email='adopter@surfur.test',
            data_processing_consent=True,
            responsible_adoption_agreement=True,
        )

    def test_platform_admin_cannot_modify_animals_or_adoptions(self):
        self.client.force_authenticate(user=self.platform_admin)

        # Read-only monitoring works
        self.assertEqual(self.client.get('/api/v1/admin-panel/animals/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get('/api/v1/admin-panel/adoptions/').status_code, status.HTTP_200_OK)

        # Mutating animals or adoptions is strictly forbidden
        res_create_pet = self.client.post(
            f'/api/v1/pets/shelter/{self.shelter_a.slug}/create/',
            {'name': 'Blocked', 'species': 'dog'},
            format='json',
        )
        self.assertEqual(res_create_pet.status_code, status.HTTP_403_FORBIDDEN)

        res_edit_pet = self.client.patch(
            f'/api/v1/pets/{self.pet_a.id}/update/',
            {'name': 'Hacked'},
            format='json',
        )
        self.assertEqual(res_edit_pet.status_code, status.HTTP_403_FORBIDDEN)

        res_delete_pet = self.client.delete(f'/api/v1/pets/{self.pet_a.id}/update/')
        self.assertEqual(res_delete_pet.status_code, status.HTTP_403_FORBIDDEN)

        res_update_inquiry = self.client.patch(
            f'/api/v1/adoptions/{self.inquiry_a.id}/status/',
            {'status': 'approved'},
            format='json',
        )
        self.assertEqual(res_update_inquiry.status_code, status.HTTP_403_FORBIDDEN)

    def test_shelter_admin_isolation_and_permissions(self):
        # Shelter B cannot access Admin Panel
        self.client.force_authenticate(user=self.shelter_admin_b)
        self.assertEqual(self.client.get('/api/v1/admin-panel/dashboard/').status_code, status.HTTP_403_FORBIDDEN)

        # Shelter B cannot edit Shelter A's pet or inquiry
        self.assertEqual(
            self.client.patch(f'/api/v1/pets/{self.pet_a.id}/update/', {'name': 'Stolen'}, format='json').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.patch(
                f'/api/v1/adoptions/{self.inquiry_a.id}/status/',
                {'status': 'approved'},
                format='json',
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )

        # Shelter A CAN manage its own pet and inquiry
        self.client.force_authenticate(user=self.shelter_admin_a)
        res_ok = self.client.patch(
            f'/api/v1/adoptions/{self.inquiry_a.id}/status/',
            {'status': 'approved', 'notes': 'Looks great!'},
            format='json',
        )
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)

    def test_adopter_cannot_access_admin_or_promote_self(self):
        self.client.force_authenticate(user=self.adopter)
        self.assertEqual(self.client.get('/api/v1/admin-panel/dashboard/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/v1/shelters/my-shelter/').status_code, status.HTTP_403_FORBIDDEN)

        self.client.patch('/api/v1/auth/profile/', {'role': 'platform_admin'}, format='json')
        self.adopter.refresh_from_db()
        self.assertEqual(self.adopter.role, User.Role.ADOPTER)

    def test_shelter_suspension_hides_public_visibility_and_preserves_records(self):
        self.client.force_authenticate(user=self.platform_admin)
        res_suspend = self.client.post(
            f'/api/v1/admin-panel/shelters/{self.shelter_a.id}/action/',
            {'action': 'suspend', 'reason': 'Inspection'},
            format='json',
        )
        self.assertEqual(res_suspend.status_code, status.HTTP_200_OK)

        # Public endpoints hide suspended shelter and its pets
        anon = APIClient()
        shelters_res = anon.get('/api/v1/shelters/').data['results']
        self.assertFalse(any(s['id'] == str(self.shelter_a.id) for s in shelters_res))
        pets_res = anon.get('/api/v1/pets/').data['results']
        self.assertFalse(any(p['id'] == str(self.pet_a.id) for p in pets_res))

        # Underlying pet & inquiry records remain preserved
        self.pet_a.refresh_from_db()
        self.assertEqual(self.pet_a.adoption_status, Pet.AdoptionStatus.AVAILABLE)
        self.assertTrue(AdoptionInquiry.objects.filter(id=self.inquiry_a.id).exists())
        self.assertTrue(AuditLog.objects.filter(action='shelter_suspend').exists())

        # Reactivate restores visibility
        self.client.post(
            f'/api/v1/admin-panel/shelters/{self.shelter_a.id}/action/',
            {'action': 'reactivate'},
            format='json',
        )
        shelters_after = anon.get('/api/v1/shelters/').data['results']
        self.assertTrue(any(s['id'] == str(self.shelter_a.id) for s in shelters_after))

    def test_create_platform_admin_management_command(self):
        out = StringIO()
        call_command(
            'create_platform_admin',
            email='owner@surfur.ph',
            full_name='SurFur Owner',
            password='OwnerSecurePassword!2026',
            stdout=out,
        )
        created = User.objects.get(email='owner@surfur.ph')
        self.assertEqual(created.role, User.Role.PLATFORM_ADMIN)
        self.assertFalse(created.is_superuser)
        self.assertFalse(created.is_staff)

    def test_audit_logs_enriched_filtering_and_export(self):
        AuditLog.objects.create(
            actor_email=self.platform_admin.email,
            action='user_password_reset_initiated',
            resource_type='User',
            resource_id=str(self.adopter.id),
            metadata={'target_email': self.adopter.email, 'token': 'should-be-stripped'},
        )
        # Adopter and Shelter Admin cannot access audit logs
        self.client.force_authenticate(user=self.adopter)
        self.assertEqual(self.client.get('/api/v1/admin-panel/audit-logs/').status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(user=self.shelter_admin_a)
        self.assertEqual(self.client.get('/api/v1/admin-panel/audit-logs/').status_code, status.HTTP_403_FORBIDDEN)

        # Platform Admin receives enriched actor/resource info and summary without sensitive tokens
        self.client.force_authenticate(user=self.platform_admin)
        res = self.client.get('/api/v1/admin-panel/audit-logs/', {'page_size': 10, 'resource_type': 'User'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('summary', res.data)
        row = res.data['results'][0]
        self.assertEqual(row['actor_name'], self.platform_admin.full_name)
        self.assertEqual(row['actor_role'], 'platform_admin')
        self.assertEqual(row['resource_name'], self.adopter.full_name)
        self.assertNotIn('token', row['metadata'])

        csv_res = self.client.get('/api/v1/admin-panel/audit-logs/export/')
        self.assertEqual(csv_res.status_code, status.HTTP_200_OK)
        self.assertEqual(csv_res['Content-Type'], 'text/csv')
