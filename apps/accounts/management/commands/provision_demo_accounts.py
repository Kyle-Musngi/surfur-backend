from django.core.management.base import BaseCommand
from apps.accounts.provisioning import provision_demo_accounts_from_env


class Command(BaseCommand):
    help = 'Idempotently provision @surfur.test evaluation accounts from environment variables.'

    def handle(self, *args, **options):
        results = provision_demo_accounts_from_env()
        if not results:
            self.stdout.write(self.style.WARNING('No DEMO_*_PASSWORD environment variables configured; skipped.'))
            return
        for item in results:
            self.stdout.write(self.style.SUCCESS(item))
