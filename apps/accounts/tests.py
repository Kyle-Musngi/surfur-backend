import os
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.accounts.provisioning import provision_demo_accounts_from_env
from apps.core.models import CebuLocation
from apps.shelters.models import Shelter

User = get_user_model()


class DemoAccountProvisioningTests(TestCase):
    def setUp(self):
        self.city = CebuLocation.objects.create(
            name='Cebu City',
            location_type='city',
            province='Cebu',
            latitude='10.3157',
            longitude='123.8854',
        )
        self.shelter1 = Shelter.objects.create(
            name='[DEMO] Island Paws Animal Rescue Cebu',
            slug='island-paws-rescue-cebu-demo',
            address='Banilad, Cebu City',
            city=self.city,
            latitude='10.3400',
            longitude='123.9100',
            email='demo1@example.test',
            verification_status='verified',
            is_demo=True,
        )
        self.shelter2 = Shelter.objects.create(
            name='[DEMO] Lapu-Lapu Coastal Felines & Hounds',
            slug='lapu-lapu-coastal-felines-demo',
            address='Maribago, Lapu-Lapu City',
            city=self.city,
            latitude='10.2880',
            longitude='123.9850',
            email='demo2@example.test',
            verification_status='pending',
            is_demo=True,
        )

    def test_provisions_all_five_accounts_without_duplicates_or_unnecessary_resets(self):
        env = {
            'DEMO_ADMIN_PASSWORD': 'UnitTestAdminPass!1',
            'DEMO_SHELTER_PASSWORD': 'UnitTestShelterPass!1',
            'DEMO_SHELTER2_PASSWORD': 'UnitTestShelterPass!2',
            'DEMO_ADOPTER_PASSWORD': 'UnitTestAdopterPass!1',
            'DEMO_ADOPTER2_PASSWORD': 'UnitTestAdopterPass!2',
        }
        with patch.dict(os.environ, env, clear=False):
            first = provision_demo_accounts_from_env()
            self.assertEqual(len(first), 5)
            self.assertTrue(all(item.startswith('created:') for item in first))

            admin_user = User.objects.get(email='admin@surfur.test')
            self.assertEqual(admin_user.role, 'platform_admin')
            self.assertTrue(admin_user.is_staff)
            self.assertFalse(admin_user.is_superuser)
            self.assertTrue(admin_user.check_password('UnitTestAdminPass!1'))

            s1_user = User.objects.get(email='shelter@surfur.test')
            s2_user = User.objects.get(email='shelter2@surfur.test')
            self.assertTrue(self.shelter1.administrators.filter(pk=s1_user.pk).exists())
            self.assertTrue(self.shelter2.administrators.filter(pk=s2_user.pk).exists())

            old_hash = admin_user.password
            second = provision_demo_accounts_from_env()
            self.assertTrue(all(item.startswith('unchanged:') for item in second))
            admin_user.refresh_from_db()
            self.assertEqual(admin_user.password, old_hash)
            self.assertEqual(User.objects.filter(email='admin@surfur.test').count(), 1)

    def test_skips_when_env_vars_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            results = provision_demo_accounts_from_env()
            self.assertEqual(results, [])
