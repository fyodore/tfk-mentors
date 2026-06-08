"""Send due ScheduledEmail rows to mentors."""

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import ScheduledEmail


def default_subject(scheduled_email):
    year = scheduled_email.resolve_season_year()
    if year:
        return f"TFK Mentors — {year} NYC Marathon season"
    return "TFK Mentors — practice confirmation"


def due_scheduled_emails():
    return (
        ScheduledEmail.objects.filter(
            task_completed_at__isnull=True,
            scheduled_send_at__lte=timezone.now(),
        )
        .select_related("recipient_season")
        .prefetch_related("practices")
        .order_by("scheduled_send_at", "id")
    )


def send_scheduled_email(scheduled_email, *, dry_run=False):
    """
    Send one scheduled email to all target mentors.
    Marks task_completed_at when every message is sent successfully.
    """
    scheduled_email.sync_mentor_tokens()
    mentors = list(scheduled_email.get_target_mentors())
    if not mentors:
        raise ValueError(
            f"ScheduledEmail {scheduled_email.pk} has no recipients."
        )

    subject = default_subject(scheduled_email)
    if dry_run:
        return {"sent": 0, "recipients": len(mentors), "subject": subject}

    with transaction.atomic():
        for mentor in mentors:
            body = scheduled_email.render_body_for_mentor(mentor)
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[mentor.email],
                fail_silently=False,
            )
        scheduled_email.task_completed_at = timezone.now()
        scheduled_email.save(update_fields=["task_completed_at", "updated_at"])

    return {"sent": len(mentors), "recipients": len(mentors), "subject": subject}
