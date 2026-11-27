import sys
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    verbose_name = 'Accounts'

    def ready(self):
        skip_cmds = {'makemigrations', 'migrate', 'collectstatic', 'test'}
        if any(cmd in sys.argv for cmd in skip_cmds):
            return
        from apps.accounts.provisioning import safe_provision_demo_accounts_on_boot
        safe_provision_demo_accounts_on_boot()
