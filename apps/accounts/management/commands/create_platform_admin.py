import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from apps.accounts.models import User


class Command(BaseCommand):
    help = 'Securely create the initial Platform Administrator account (no hardcoded credentials).'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, help='Platform Administrator email address')
        parser.add_argument('--full-name', type=str, help='Platform Administrator full name')
        parser.add_argument(
            '--password',
            type=str,
            help='Password (prefer interactive prompt if omitted so it is not stored in shell history)',
        )

    def handle(self, *args, **options):
        email = (options.get('email') or '').strip()
        full_name = (options.get('full_name') or '').strip()
        password = options.get('password')

        if not email:
            email = input('Platform Administrator Email: ').strip()
        if not email:
            raise CommandError('Email is required.')

        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(f'A user with email "{email}" already exists.')

        if not full_name:
            full_name = input('Full Name: ').strip()
        if not full_name:
            raise CommandError('Full name is required.')

        if not password:
            password = getpass.getpass('Password: ')
            password_confirm = getpass.getpass('Confirm Password: ')
            if password != password_confirm:
                raise CommandError('Passwords do not match.')

        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(' '.join(exc.messages))

        user = User.objects.create_user(
            email=email,
            full_name=full_name,
            password=password,
            role=User.Role.PLATFORM_ADMIN,
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Platform Administrator account created successfully for {user.email} (role={user.role}).'
            )
        )

