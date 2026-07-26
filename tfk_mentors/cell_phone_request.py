"""Email assigned mentors who are missing a cell phone number."""

from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .email_sending import _verify_email_delivery
from .models import (
    Mentor,
    MentorCellPhoneRequestSend,
    MentorCellPhoneRequestToken,
    Practice,
)

CELL_PHONE_REQUEST_SUBJECT = "TFK Mentor information needed"

CELL_PHONE_REQUEST_BODY = """You have indicated you are available for practice and been assigned to at least one. Coaches need cell phones for everyone attending as a mentor. Please click on the link below and enter your cell phone number.

{link}

Thank you,
Ted"""


def mentors_assigned_without_cell_phone(*, season_id=None):
    """Mentors on an attending practice roster with no cell phone on file."""
    practices = Practice.objects.all().order_by("date", "id")
    if season_id is not None:
        practices = practices.filter(season_id=season_id)

    mentor_ids = set()
    for practice in practices:
        mentor_ids.update(practice.assigned_mentor_ids())
    if not mentor_ids:
        return Mentor.objects.none()

    mentors = list(
        Mentor.objects.filter(pk__in=mentor_ids).order_by(
            "last_name", "first_name", "id"
        )
    )
    missing_ids = [
        mentor.id for mentor in mentors if not (mentor.cell_phone or "").strip()
    ]
    if not missing_ids:
        return Mentor.objects.none()
    return Mentor.objects.filter(pk__in=missing_ids).order_by(
        "last_name", "first_name", "id"
    )


def serialize_missing_mentor(mentor):
    return {
        "id": mentor.id,
        "first_name": mentor.first_name,
        "last_name": mentor.last_name,
        "email": mentor.email,
        "type": mentor.type,
        "cell_phone": mentor.cell_phone or "",
    }


def render_cell_phone_request_body(token):
    return CELL_PHONE_REQUEST_BODY.format(link=token.absolute_url())


def send_cell_phone_requests(*, season_id=None, dry_run=False):
    """
    Email each assigned mentor without a cell phone a unique one-time link.

    Creates a MentorCellPhoneRequestSend batch and per-mentor tokens.
    """
    mentors = list(mentors_assigned_without_cell_phone(season_id=season_id))
    if not mentors:
        raise ValueError(
            "No assigned mentors are missing a cell phone for this selection."
        )

    if dry_run:
        return {
            "sent": 0,
            "recipients": len(mentors),
            "subject": CELL_PHONE_REQUEST_SUBJECT,
            "sample_body": CELL_PHONE_REQUEST_BODY.format(
                link="https://example.com/mentor-cell-phone?token=…"
            ),
            "mentors": [serialize_missing_mentor(m) for m in mentors],
        }

    _verify_email_delivery()
    now = timezone.now()

    with transaction.atomic():
        batch = MentorCellPhoneRequestSend.objects.create(
            season_id=season_id,
            sent_at=now,
            recipients_emailed_count=0,
        )
        tokens = []
        for mentor in mentors:
            tokens.append(
                MentorCellPhoneRequestToken(
                    send=batch,
                    mentor=mentor,
                    sent_at=now,
                )
            )
        MentorCellPhoneRequestToken.objects.bulk_create(tokens)
        tokens = list(
            MentorCellPhoneRequestToken.objects.filter(send=batch).select_related(
                "mentor"
            )
        )

        for token in tokens:
            send_mail(
                subject=CELL_PHONE_REQUEST_SUBJECT,
                message=render_cell_phone_request_body(token),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[token.mentor.email],
                fail_silently=False,
            )

        batch.recipients_emailed_count = len(tokens)
        batch.save(update_fields=["recipients_emailed_count", "updated_at"])

    return {
        "sent": len(tokens),
        "recipients": len(tokens),
        "subject": CELL_PHONE_REQUEST_SUBJECT,
        "send_id": batch.id,
        "sent_at": batch.sent_at.isoformat(),
    }
