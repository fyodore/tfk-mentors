"""Notify coaches when a mentor swap happens after the practice reminder was sent."""

from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail

from .email_sending import _verify_email_delivery
from .models import Coach, PracticeReminderEmail, Season
from .practice_reminder import format_practice_date


def last_reminder_for_practice(practice):
    """
    Reminder that last covers this practice (listed as practice_one).

    That email is the final practice-info reminder coaches receive for the session.
    """
    return (
        PracticeReminderEmail.objects.filter(practice_one_id=practice.id)
        .order_by("-scheduled_send_at", "-id")
        .first()
    )


def practice_last_reminder_already_sent(practice):
    reminder = last_reminder_for_practice(practice)
    return reminder is not None and reminder.task_completed_at is not None


def coaches_for_swap_notification(practice):
    """
    All coaches for the practice season, plus the season head coach.

    Dedupes by coach id so the head coach is not listed twice when also in season.
    """
    coaches = []
    seen_ids = set()

    def add(coach):
        if coach is None or coach.id in seen_ids:
            return
        if not (coach.email or "").strip():
            return
        seen_ids.add(coach.id)
        coaches.append(coach)

    for coach in Coach.objects.filter(seasons=practice.season_id).order_by(
        "last_name", "first_name", "id"
    ):
        add(coach)

    season = (
        Season.objects.select_related("head_coach")
        .filter(pk=practice.season_id)
        .first()
    )
    if season is not None:
        add(season.head_coach)

    return coaches


def mentor_display_name(mentor):
    return f"{mentor.first_name} {mentor.last_name}".strip()


def swap_notification_subject(practice):
    return f"Mentor swap for TFK practice {format_practice_date(practice)}"


def swap_notification_body(practice, outgoing, incoming, pace):
    practice_when = format_practice_date(practice)
    cell = (incoming.cell_phone or "").strip() or "(not on file)"
    pace_text = (pace or "").strip() or "(not set)"
    return (
        f"{mentor_display_name(incoming)} is replacing "
        f"{mentor_display_name(outgoing)} for the practice on {practice_when}.\n"
        f"\n"
        f"Pace: {pace_text}\n"
        f"Cell phone: {cell}\n"
    )


def swap_confirmation_subject():
    return "TFK Mentor Swap Confirmation"


def swap_confirmation_body(practice, outgoing, incoming):
    practice_when = format_practice_date(practice)
    return (
        f"This is your confirmation that {mentor_display_name(outgoing)} has been "
        f"replaced with {mentor_display_name(incoming)} for the {practice_when}.  "
        f"If this was made in error please reply to this email."
    )


def send_mentor_swap_confirmations(
    practice,
    outgoing,
    incoming,
    *,
    dry_run=False,
):
    """Send separate swap confirmation emails to the outgoing and incoming mentors."""
    subject = swap_confirmation_subject()
    body = swap_confirmation_body(practice, outgoing, incoming)
    recipients = []
    for mentor in (outgoing, incoming):
        email = (mentor.email or "").strip()
        if email:
            recipients.append(email)

    if dry_run or not recipients:
        return {
            "sent": 0,
            "recipients": len(recipients),
            "subject": subject,
            "skipped": not recipients,
        }

    _verify_email_delivery()

    for email in recipients:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

    return {
        "sent": len(recipients),
        "recipients": len(recipients),
        "subject": subject,
        "skipped": False,
    }


def send_mentor_swap_coach_notification(
    practice,
    outgoing,
    incoming,
    pace,
    *,
    dry_run=False,
):
    """
    Email all season coaches and the head coach about a mentor swap in one message.

    Only call when the last reminder for the practice has already been sent.
    """
    coaches = coaches_for_swap_notification(practice)
    recipient_list = [coach.email.strip() for coach in coaches]
    subject = swap_notification_subject(practice)
    body = swap_notification_body(practice, outgoing, incoming, pace)

    if dry_run or not recipient_list:
        return {
            "sent": 0,
            "recipients": len(recipient_list),
            "subject": subject,
            "skipped": not recipient_list,
        }

    _verify_email_delivery()

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipient_list,
        fail_silently=False,
    )

    return {
        "sent": 1,
        "recipients": len(recipient_list),
        "subject": subject,
        "skipped": False,
    }
