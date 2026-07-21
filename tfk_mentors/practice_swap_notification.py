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


def coaches_for_swap_notification(practice):
    """
    Coaches assigned to this practice, plus the season head coach.

    Dedupes by coach id so the head coach is not emailed twice when also assigned.
    """
    from .models import Season

    coaches = []
    seen_ids = set()

    def add(coach):
        if coach is None or coach.id in seen_ids:
            return
        if not (coach.email or "").strip():
            return
        seen_ids.add(coach.id)
        coaches.append(coach)

    for assignment in (
        CoachPracticeAssignment.objects.filter(practice=practice)
        .select_related("coach")
        .order_by("coach__last_name", "coach__first_name", "coach__id")
    ):
        add(assignment.coach)

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


def send_mentor_swap_coach_notification(
    practice,
    outgoing,
    incoming,
    pace,
    *,
    dry_run=False,
):
    """
    Email practice coaches and the season head coach about a mentor swap.

    Only call when the last reminder for the practice has already been sent.
    """
    coaches = coaches_for_swap_notification(practice)
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
