from .models import AuditLog


def get_client_ip(request):
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_audit_event(request_or_user, action, resource_type, resource_id='', metadata=None):
    """
    Create an immutable audit log entry without recording sensitive secrets/passwords.
    """
    actor_email = ''
    ip_address = None

    if hasattr(request_or_user, 'user'):
        user = request_or_user.user
        ip_address = get_client_ip(request_or_user)
    else:
        user = request_or_user

    if user and getattr(user, 'is_authenticated', False):
        actor_email = getattr(user, 'email', '') or ''
    elif isinstance(user, str):
        actor_email = user

    safe_meta = {}
    if isinstance(metadata, dict):
        blocked_keys = {'password', 'password_confirm', 'token', 'access', 'refresh', 'secret'}
        for k, v in metadata.items():
            if str(k).lower() not in blocked_keys:
                safe_meta[k] = v

    return AuditLog.objects.create(
        actor_email=actor_email,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else '',
        metadata=safe_meta,
        ip_address=ip_address,
    )

