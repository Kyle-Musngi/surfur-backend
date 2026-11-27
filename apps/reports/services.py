import hashlib
import hmac
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from apps.notifications.models import Notification
from apps.reports.models import StrayReport

STATUS_MESSAGES = {
    'submitted': (
        'Stray Report Received',
        'Your stray animal report #{ref} has been received and logged for review.',
    ),
    'under_review': (
        'Stray Report Under Review',
        'Your stray animal report #{ref} is currently under review by SurFur coordinators.',
    ),
    'assigned': (
        'Rescue Organization Assigned',
        'Your stray animal report #{ref} has been assigned to {org} for rescue coordination.',
    ),
    'rescue_in_progress': (
        'Rescue Operation in Progress',
        'Rescue operations are currently in progress for your stray report #{ref}.',
    ),
    'rescued': (
        'Stray Animal Successfully Rescued!',
        'Good news! The stray animal you reported (#{ref}) has been successfully rescued. Thank you for helping make a difference through SurFur.',
    ),
    'resolved': (
        'Stray Report Resolved',
        'Your stray animal report #{ref} has been marked as resolved.',
    ),
    'unable_to_locate': (
        'Rescue Update: Unable to Locate',
        'Responders could not locate the animal for report #{ref}. Please submit additional details if sighted again.',
    ),
    'rejected': (
        'Stray Report Closed',
        'Your stray animal report #{ref} could not be verified or was marked invalid.',
    ),
    'duplicate': (
        'Stray Report Marked as Duplicate',
        'Your stray animal report #{ref} matches an existing active report already being coordinated.',
    ),
    'cancelled': (
        'Stray Report Cancelled',
        'Your stray animal report #{ref} has been cancelled.',
    ),
}


def hash_token(raw_token: str) -> str:
    return hashlib.sha256((raw_token or '').encode('utf-8')).hexdigest()


def verify_token(raw_token: str, stored_hash: str) -> bool:
    if not raw_token or not stored_hash:
        return False
    return hmac.compare_digest(hash_token(raw_token), stored_hash)


def send_guest_verification_email(report, raw_verification_token: str):
    if not report.reporter_email:
        return False
    verify_url = f'{settings.FRONTEND_URL}/report/verify?ref={report.report_number}&token={raw_verification_token}'
    try:
        send_mail(
            subject=f'[SurFur] Verify Contact for Stray Report {report.report_number}',
            message=(
                f'Hello {report.reporter_name or "Friend"},\n\n'
                f'Thank you for submitting stray report {report.report_number}.\n'
                f'Please verify your email address within 24 hours so we can send you rescue status updates:\n'
                f'{verify_url}\n'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[report.reporter_email],
            fail_silently=True,
        )
        return True
    except Exception:
        return False


def detect_potential_duplicate(report) -> bool:
    """Flag potential recent duplicates in the same city & species for admin review (never auto-deletes)."""
    if not report.city_id:
        return False
    since = timezone.now() - timedelta(hours=48)
    candidates = StrayReport.objects.filter(
        city_id=report.city_id,
        animal_type=report.animal_type,
        created_at__gte=since,
    ).exclude(pk=report.pk)
    if candidates.exists():
        report.is_potential_duplicate = True
        report.duplicate_flag_reason = 'Similar recent report in the same municipality and species within 48 hours.'
        report.save(update_fields=['is_potential_duplicate', 'duplicate_flag_reason'])
        return True
    return False


def notify_stray_report_status(report, new_status: str, old_status: str = ''):
    """
    Create an in-app notification for registered reporters, and send email notifications
    for opted-in registered users or verified guest reporters.
    """
    if old_status and old_status == new_status:
        return

    org_name = report.assigned_organization.name if report.assigned_organization else 'a partner rescue organization'
    title_tpl, msg_tpl = STATUS_MESSAGES.get(
        new_status,
        ('Stray Report Update', f'Your stray animal report #{{ref}} status is now "{report.get_status_display()}".'),
    )
    title = title_tpl
    message = msg_tpl.format(ref=report.report_number, org=org_name)

    if report.reporter:
        latest = Notification.objects.filter(
            user=report.reporter,
            related_resource_type='stray_report',
            related_resource_id=str(report.id),
        ).first()
        if latest and latest.title == title and latest.message == message:
            return

        Notification.objects.create(
            user=report.reporter,
            notification_type=Notification.NotificationType.SYSTEM,
            title=title,
            message=message,
            related_resource_type='stray_report',
            related_resource_id=str(report.id),
        )

        if report.reporter.email_notifications and report.reporter.email:
            try:
                send_mail(
                    subject=f'[SurFur] {title} ({report.report_number})',
                    message=f'Hello {report.reporter.full_name},\n\n{message}\n\nTrack your report at {settings.FRONTEND_URL}/my-reports\n',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[report.reporter.email],
                    fail_silently=True,
                )
            except Exception:
                pass
    elif report.contact_verified and report.data_processing_consent and report.reporter_email:
        try:
            send_mail(
                subject=f'[SurFur] {title} ({report.report_number})',
                message=(
                    f'Hello {report.reporter_name or "Reporter"},\n\n'
                    f'{message}\n\n'
                    f'Track your report status securely at {settings.FRONTEND_URL}/report/track?ref={report.report_number}\n'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[report.reporter_email],
                fail_silently=True,
            )
        except Exception:
            pass
