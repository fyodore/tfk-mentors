"""Notify coaches when a mentor swap happens after the practice reminder was sent."""

from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail

from .email_sending import _verify_email_delivery
from .models import CoachPracticeAssignment, PracticeReminderEmail
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


def coaches_assigned_to_practice(practice):
    """Coaches going to this practice who have an email address."""
    coaches = []
    for assignment in (
        CoachPracticeAssignment.objects.filter(practice=practice)
        .select_related("coach")
        .order_by("coach__last_name", "coach__first_name", "coach__id")
    ):
        coach = assignment.coach
        if (coach.email or "").strip():
            coaches.append(coach)
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


def send_mentor_swap_coach_notification(
    practice,
    outgoing,
    incoming,
    pace,
    *,
    dry_run=False,
):
    """
    Email coaches assigned to the practice about a mentor swap.

    Only call when the last reminder for the practice has already been sent.
    """
    coaches = coaches_assigned_to_practice(practice)
    subject = swap_notification_subject(practice)
    body = swap_notification_body(practice, outgoing, incoming, pace)

    if dry_run or not coaches:
        return {
            "sent": 0,
            "recipients": len(coaches),
            "subject": subject,
            "skipped": not coaches,
        }

    _verify_email_delivery()

    for coach in coaches:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[coach.email],
            fail_silently=False,
        )

    return {
        "sent": len(coaches),
        "recipients": len(coaches),
        "subject": subject,
        "skipped": False,
    }
