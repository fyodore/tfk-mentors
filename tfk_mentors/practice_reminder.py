"""Practice reminder emails sent after each practice about upcoming sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .email_sending import _verify_email_delivery
from .models import (
    Coach,
    Mentor,
    MentorTypes,
    PaceTypes,
    Practice,
    PracticeReminderEmail,
    PracticeReminderSendRecord,
    Season,
    TfkStaff,
    normalize_pace,
)

PACE_GROUPS = [choice.value for choice in PaceTypes]

DEFAULT_BODY_TEMPLATE = """Dear {{first_name}},

If you haven't done so, please join our facebook group: https://www.facebook.com/groups/{{year}}tfkmentors/.

{{practice_1_section}}

{{mentor_practice_1_notice}}

{{practice_2_section}}

{{mentor_practice_2_notice}}"""


def display_time_zone():
    return ZoneInfo(getattr(settings, "TIME_ZONE", "America/Chicago"))


def format_practice_date(practice):
    when = practice.date
    if timezone.is_naive(when):
        when = timezone.make_aware(when, display_time_zone())
    local = timezone.localtime(when, display_time_zone())
    return local.strftime("%A, %B %d, %Y, %I:%M %p").replace(" 0", " ")


def morning_after_practice(practice_dt):
    if timezone.is_naive(practice_dt):
        practice_dt = timezone.make_aware(practice_dt, display_time_zone())
    local = timezone.localtime(practice_dt, display_time_zone())
    next_day = (local + timedelta(days=1)).replace(
        hour=6, minute=15, second=0, microsecond=0
    )
    return next_day


def default_subject(practice_one, practice_two):
    date_one = format_practice_date(practice_one)
    if practice_two is None:
        return f"TFK Practice {date_one} Info"
    date_two = format_practice_date(practice_two)
    return f"TFK Practices {date_one} & {date_two} Info"


def _contact_line(first_name, last_name, email, phone):
    phone_text = f"  {phone}".rstrip() if phone else ""
    return f"\t{first_name} {last_name}: {email}{phone_text}"


def _coaches_for_practice(practice):
    rows = []
    for assignment in (
        practice.coachpracticeassignment_set.select_related("coach")
        .order_by("coach__last_name", "coach__first_name", "coach__id")
    ):
        coach = assignment.coach
        rows.append(
            _contact_line(coach.first_name, coach.last_name, coach.email, coach.cell)
        )
    return rows


def _mentors_for_practice_by_pace(practice):
    from .models import Practice as PracticeModel

    practice = (
        PracticeModel.objects.filter(pk=practice.pk)
        .prefetch_related("mentor_email_replies__mentor")
        .first()
    )
    replies = practice.latest_attending_mentor_replies()
    by_pace = {pace: [] for pace in PACE_GROUPS}
    for reply in replies:
        mentor = reply.mentor
        pace = normalize_pace(reply.pace or mentor.pace or "")
        if pace not in by_pace:
            continue
        by_pace[pace].append(
            _contact_line(
                mentor.first_name,
                mentor.last_name,
                mentor.email,
                mentor.cell_phone,
            )
        )
    return by_pace


def build_practice_section(practice):
    if practice is None:
        return ""
    lines = [
        f"Practice {format_practice_date(practice)}",
        f"Plan: {practice.description.strip() if practice.description else '—'}",
        f"Location: {practice.start_location.strip() if practice.start_location else '—'}",
        "",
        "Coaches:",
    ]
    coach_lines = _coaches_for_practice(practice)
    lines.extend(coach_lines if coach_lines else ["\t(none listed)"])
    lines.append("")
    lines.append("Mentors:")
    mentors_by_pace = _mentors_for_practice_by_pace(practice)
    for pace in PACE_GROUPS:
        lines.append(f"\t{pace} min per mile pace group")
        pace_rows = mentors_by_pace.get(pace) or []
        if pace_rows:
            lines.extend(pace_rows)
        else:
            lines.append("\t\t(none listed)")
    return "\n".join(lines)


def mentor_schedule_notice(recipient, practice):
    if recipient.mentor_id is None or practice is None:
        return ""
    assignment = (
        practice.mentorpracticeassignment_set.filter(mentor_id=recipient.mentor_id)
        .first()
    )
    reply = None
    for item in practice.latest_attending_mentor_replies():
        if item.mentor_id == recipient.mentor_id:
            reply = item
            break
    if assignment is None and reply is None:
        return ""
    pace = ""
    if reply is not None:
        pace = normalize_pace(reply.pace or reply.mentor.pace or "")
    elif assignment is not None:
        pace = normalize_pace(assignment.pace or "")
    if not pace:
        return ""
    return (
        "You are scheduled to mentor:\n"
        f"\t{format_practice_date(practice)} in the {pace} pace group"
    )


@dataclass(frozen=True)
class ReminderRecipient:
    email: str
    first_name: str
    last_name: str
    kind: str
    mentor_id: int | None = None
    coach_id: int | None = None
    staff_id: int | None = None


def collect_recipients(reminder: PracticeReminderEmail):
    season = reminder.season
    practice_ids = [
        pid
        for pid in (reminder.practice_one_id, reminder.practice_two_id)
        if pid is not None
    ]
    practices = list(
        Practice.objects.filter(pk__in=practice_ids).prefetch_related(
            "mentor_email_replies__mentor"
        )
    )
    practice_by_id = {p.id: p for p in practices}

    recipients: dict[str, ReminderRecipient] = {}

    def add(recipient: ReminderRecipient):
        key = (recipient.email or "").strip().lower()
        if not key:
            return
        recipients[key] = recipient

    for staff in TfkStaff.objects.order_by("last_name", "first_name", "id"):
        add(
            ReminderRecipient(
                email=staff.email,
                first_name=staff.first_name,
                last_name=staff.last_name,
                kind="staff",
                staff_id=staff.id,
            )
        )

    for coach in Coach.objects.filter(seasons=season).order_by(
        "last_name", "first_name", "id"
    ):
        add(
            ReminderRecipient(
                email=coach.email,
                first_name=coach.first_name,
                last_name=coach.last_name,
                kind="coach",
                coach_id=coach.id,
            )
        )

    for mentor in Mentor.objects.filter(seasons=season, type=MentorTypes.PRACTICE):
        add(
            ReminderRecipient(
                email=mentor.email,
                first_name=mentor.first_name,
                last_name=mentor.last_name,
                kind="mentor",
                mentor_id=mentor.id,
            )
        )

    remote_attending_ids = set()
    for pid in practice_ids:
        practice = practice_by_id.get(pid)
        if practice is None:
            continue
        for reply in practice.latest_attending_mentor_replies():
            if reply.mentor.type == MentorTypes.REMOTE:
                remote_attending_ids.add(reply.mentor_id)

    for mentor in Mentor.objects.filter(pk__in=remote_attending_ids).order_by(
        "last_name", "first_name", "id"
    ):
        add(
            ReminderRecipient(
                email=mentor.email,
                first_name=mentor.first_name,
                last_name=mentor.last_name,
                kind="mentor",
                mentor_id=mentor.id,
            )
        )

    return list(recipients.values())


def render_reminder_for_recipient(reminder, recipient: ReminderRecipient):
    practice_one = reminder.practice_one
    practice_two = reminder.practice_two
    year = reminder.season.year if reminder.season_id else ""

    context = {
        "first_name": recipient.first_name or "",
        "last_name": recipient.last_name or "",
        "year": str(year),
        "date_of_practice_1": format_practice_date(practice_one) if practice_one else "",
        "date_of_practice_2": format_practice_date(practice_two) if practice_two else "",
        "practice_1_section": build_practice_section(practice_one),
        "practice_2_section": build_practice_section(practice_two)
        if practice_two
        else "",
        "mentor_practice_1_notice": mentor_schedule_notice(recipient, practice_one),
        "mentor_practice_2_notice": mentor_schedule_notice(recipient, practice_two),
    }

    body = reminder.body_text
    for key, value in context.items():
        body = body.replace(f"{{{{{key}}}}}", value)

    subject = reminder.subject or default_subject(practice_one, practice_two)
    for key, value in context.items():
        subject = subject.replace(f"{{{{{key}}}}}", value)

    return subject.strip(), body.strip()


def sync_practice_reminders_for_season(season):
    if isinstance(season, int):
        season = Season.objects.get(pk=season)

    practices = list(
        Practice.objects.filter(season=season).order_by("date", "id")
    )
    created = 0
    updated = 0

    for index, anchor in enumerate(practices):
        practice_one = practices[index + 1] if index + 1 < len(practices) else None
        if practice_one is None:
            PracticeReminderEmail.objects.filter(anchor_practice=anchor).delete()
            continue

        practice_two = (
            practices[index + 2] if index + 2 < len(practices) else None
        )
        defaults = {
            "season": season,
            "practice_one": practice_one,
            "practice_two": practice_two,
            "subject": default_subject(practice_one, practice_two),
            "body_text": DEFAULT_BODY_TEMPLATE,
            "scheduled_send_at": morning_after_practice(anchor.date),
        }
        reminder, was_created = PracticeReminderEmail.objects.get_or_create(
            anchor_practice=anchor,
            defaults=defaults,
        )
        if was_created:
            created += 1
        elif reminder.task_completed_at is None:
            reminder.season = season
            reminder.practice_one = practice_one
            reminder.practice_two = practice_two
            reminder.scheduled_send_at = morning_after_practice(anchor.date)
            reminder.save(
                update_fields=[
                    "season",
                    "practice_one",
                    "practice_two",
                    "scheduled_send_at",
                    "updated_at",
                ]
            )
            updated += 1

    return {"created": created, "updated": updated, "season": season.id}


def due_practice_reminder_emails():
    return (
        PracticeReminderEmail.objects.filter(
            task_completed_at__isnull=True,
            scheduled_send_at__lte=timezone.now(),
        )
        .select_related(
            "season",
            "anchor_practice",
            "practice_one",
            "practice_two",
        )
        .order_by("scheduled_send_at", "id")
    )


def send_practice_reminder(reminder, *, dry_run=False):
    if reminder.task_completed_at:
        raise ValueError("This practice reminder has already been sent.")

    recipients = collect_recipients(reminder)
    if not recipients:
        raise ValueError("No recipients found for this practice reminder.")

    if dry_run:
        sample = recipients[0]
        subject, body = render_reminder_for_recipient(reminder, sample)
        return {
            "recipients": len(recipients),
            "subject": subject,
            "sample_body": body,
        }

    _verify_email_delivery()

    sent_count = 0
    now = timezone.now()
    with transaction.atomic():
        for recipient in recipients:
            subject, body = render_reminder_for_recipient(reminder, recipient)
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient.email],
                fail_silently=False,
            )
            PracticeReminderSendRecord.objects.create(
                reminder=reminder,
                recipient_email=recipient.email,
                recipient_first_name=recipient.first_name,
                recipient_last_name=recipient.last_name,
                recipient_kind=recipient.kind,
                rendered_subject=subject,
                rendered_body=body,
                sent_at=now,
            )
            sent_count += 1

        reminder.task_completed_at = now
        reminder.recipients_emailed_count = sent_count
        reminder.save(
            update_fields=[
                "task_completed_at",
                "recipients_emailed_count",
                "updated_at",
            ]
        )

    return {"sent": sent_count, "recipients": sent_count}
