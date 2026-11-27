import os
from django.db.utils import OperationalError, ProgrammingError


DEMO_ACCOUNT_SPECS = (
    {
        'env_var': 'DEMO_ADMIN_PASSWORD',
        'email': 'admin@surfur.test',
        'full_name': 'SurFur Administrator',
        'role': 'platform_admin',
        'is_staff': True,
        'shelter_slug': None,
    },
    {
        'env_var': 'DEMO_SHELTER_PASSWORD',
        'email': 'shelter@surfur.test',
        'full_name': 'SurFur Shelter Owner',
        'role': 'shelter_admin',
        'is_staff': False,
        'shelter_slug': 'island-paws-rescue-cebu-demo',
    },
    {
        'env_var': 'DEMO_SHELTER2_PASSWORD',
        'email': 'shelter2@surfur.test',
        'full_name': 'SurFur Shelter Owner 2',
        'role': 'shelter_admin',
        'is_staff': False,
        'shelter_slug': 'lapu-lapu-coastal-felines-demo',
    },
    {
        'env_var': 'DEMO_ADOPTER_PASSWORD',
        'email': 'adopter@surfur.test',
        'full_name': 'SurFur Adopter',
        'role': 'adopter',
        'is_staff': False,
        'shelter_slug': None,
    },
    {
        'env_var': 'DEMO_ADOPTER2_PASSWORD',
        'email': 'adopter2@surfur.test',
        'full_name': 'SurFur Adopter 2',
        'role': 'adopter',
        'is_staff': False,
        'shelter_slug': None,
    },
)


def has_demo_password_env() -> bool:
    return any(bool(os.environ.get(spec['env_var'], '').strip()) for spec in DEMO_ACCOUNT_SPECS)


def provision_demo_accounts_from_env() -> list[str]:
    """
    Idempotently provision or sync authorized @surfur.test evaluation accounts
    using passwords supplied strictly via environment variables.
    Prevents duplicate accounts and avoids unnecessary password resets when the
    stored password hash already matches the configured environment variable.
    """
    from django.contrib.auth import get_user_model
    from apps.shelters.models import Shelter

    User = get_user_model()
    processed: list[str] = []

    for spec in DEMO_ACCOUNT_SPECS:
        password = os.environ.get(spec['env_var'], '').strip()
        if not password:
            continue

        existing = User.objects.filter(email__iexact=spec['email']).first()
        created = existing is None
        if created:
            user = User(
                email=spec['email'],
                full_name=spec['full_name'],
                role=spec['role'],
                is_staff=spec['is_staff'],
                is_superuser=False,
                is_active=True,
            )
            user.set_password(password)
            user.save()
            processed.append(f"created:{spec['email']}")
        else:
            user = existing
            changed = False
            if user.full_name != spec['full_name']:
                user.full_name = spec['full_name']
                changed = True
            if user.role != spec['role']:
                user.role = spec['role']
                changed = True
            if user.is_staff != spec['is_staff']:
                user.is_staff = spec['is_staff']
                changed = True
            if not user.is_active:
                user.is_active = True
                changed = True
            if not user.has_usable_password():
                user.set_password(password)
                changed = True
            if changed:
                user.save()
                processed.append(f"updated:{spec['email']}")
            else:
                processed.append(f"unchanged:{spec['email']}")

        shelter_slug = spec['shelter_slug']
        if shelter_slug:
            shelter = Shelter.objects.filter(slug=shelter_slug).first()
            if shelter and not shelter.administrators.filter(pk=user.pk).exists():
                shelter.administrators.add(user)

    return processed


def safe_provision_demo_accounts_on_boot() -> None:
    if not has_demo_password_env():
        return
    try:
        provision_demo_accounts_from_env()
    except (OperationalError, ProgrammingError):
        # Database tables may not be migrated yet (e.g., during initial deploy).
        return
