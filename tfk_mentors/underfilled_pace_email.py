"""Email At Practice mentors when their pace group is underfilled (< 3 assigned)."""

from __future__ import annotations

from collections import defaultdict

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .email_sending import _verify_email_delivery
from .models import (
    Mentor,
    MentorTypes,
    PaceTypes,
    Practice,
    UnderfilledPaceMentorEmailSend,
    UnderfilledPaceMentorEmailToken,
    UnderfilledPaceResponseType,
    normalize_pace,
)

# Head-coach minimum assigned mentors per pace group (scheduler max may be higher).
MIN_ASSIGNED_MENTORS_PER_PACE = 3

UNDERFILLED_PACE_EMAIL_SUBJECT = (
    "Need for mentors at specific practices in your pace group"
)

UNDERFILLED_PACE_EMAIL_BODY = """After scheduling everyone some practices in your pace group have less than 3 mentor assigned.

I hope that we can get to that number for each practice.  

Below are all the practices that need additional mentors:

{practice_list}

{link}

Thank you in advance!

Ted"""

THANK_YOU_AFTER_SUBMIT = (
    "Thank you!  If you need to make any changes please reach out to Ted"
)

ALL_FILLED_MESSAGE = (
    "Thank you for coming to volunteer to mentor at a practice.  "
    "Good news!  Your fellow mentors in your pace group already signed up "
    "and filled all the slots!"
)


def format_practice_label(practice):
    """Format as 'Tue, Aug 5, 2026 - 6:30 AM' in the active timezone."""
    local = timezone.localtime(practice.date)
    hour = local.strftime("%I").lstrip("0") or "12"
    return (
        f"{local.strftime('%a, %b')} {local.day}, {local.year} "
        f"- {hour}:{local.strftime('%M %p')}"
    )


def _pace_assigned_counts(practice):
    """Map normalized pace → assigned (attending) mentor count for a practice."""
    counts = defaultdict(int)
    for _mentor, pace, _reply, _assignment in practice.attending_mentor_roster_entries():
        normalized = normalize_pace(pace or "")
        if normalized:
            counts[normalized] += 1
    return counts


def slots_remaining_for_pace(practice, pace):
    pace = normalize_pace(pace or "")
    if not pace:
        return 0
    assigned = _pace_assigned_counts(practice).get(pace, 0)
    return max(0, MIN_ASSIGNED_MENTORS_PER_PACE - assigned)


def upcoming_practices_for_season(season_id):
    today = timezone.localdate()
    qs = Practice.objects.filter(date__date__gte=today).order_by("date", "id")
    if season_id is not None:
        qs = qs.filter(season_id=season_id)
    return list(qs)


def underfilled_practice_rows_for_season(season_id):
    """Upcoming practices with any pace group below the minimum assigned count."""
    rows = []
    for practice in upcoming_practices_for_season(season_id):
        counts = _pace_assigned_counts(practice)
        underfilled = []
        for pace in (choice.value for choice in PaceTypes):
            assigned = counts.get(pace, 0)
            if assigned < MIN_ASSIGNED_MENTORS_PER_PACE:
                underfilled.append(
                    {
                        "pace": pace,
                        "assigned_count": assigned,
                        "slots_remaining": MIN_ASSIGNED_MENTORS_PER_PACE - assigned,
                    }
                )
        if underfilled:
            rows.append(
                {
                    "practice": practice,
                    "practice_id": practice.id,
                    "label": format_practice_label(practice),
                    "underfilled_pace_groups": underfilled,
                }
            )
    return rows


def practices_needing_mentors_for_mentor(mentor, *, season_id):
    """
    Upcoming practices where the mentor's profile pace is underfilled and the
    mentor is not already assigned (available does not count as assigned).
    """
    pace = normalize_pace(mentor.pace or "")
    if not pace or pace not in {choice.value for choice in PaceTypes}:
        return []
    if mentor.type != MentorTypes.PRACTICE:
        return []

    result = []
    for practice in upcoming_practices_for_season(season_id):
        if mentor.id in practice.assigned_mentor_ids():
            continue
        slots = slots_remaining_for_pace(practice, pace)
        if slots <= 0:
            continue
        result.append(
            {
                "practice": practice,
                "practice_id": practice.id,
                "label": format_practice_label(practice),
                "slots_remaining": slots,
                "pace": pace,
            }
        )
    return result


def eligible_mentors_with_practices(*, season_id):
    """At Practice mentors in season who have at least one underfilled practice to offer."""
    mentors = (
        Mentor.objects.filter(
            type=MentorTypes.PRACTICE,
            seasons__id=season_id,
        )
        .distinct()
        .order_by("last_name", "first_name", "id")
    )
    eligible = []
    for mentor in mentors:
        practices = practices_needing_mentors_for_mentor(mentor, season_id=season_id)
        if not practices:
            continue
        eligible.append({"mentor": mentor, "practices": practices})
    return eligible


def serialize_eligible_mentor(entry):
    mentor = entry["mentor"]
    return {
        "id": mentor.id,
        "first_name": mentor.first_name,
        "last_name": mentor.last_name,
        "email": mentor.email,
        "type": mentor.type,
        "pace": normalize_pace(mentor.pace or ""),
        "practices": [
            {
                "practice_id": row["practice_id"],
                "label": row["label"],
                "slots_remaining": row["slots_remaining"],
            }
            for row in entry["practices"]
        ],
    }


def render_underfilled_pace_email_body(token, practice_labels):
    practice_list = "\n".join(practice_labels) if practice_labels else "(none)"
    return UNDERFILLED_PACE_EMAIL_BODY.format(
        practice_list=practice_list,
        link=token.absolute_url(),
    )


def send_underfilled_pace_emails(*, season_id, dry_run=False):
    """Email eligible mentors; recipients are computed at send time."""
    if season_id is None:
        raise ValueError("Select a season to send underfilled pace emails.")

    eligible = eligible_mentors_with_practices(season_id=season_id)
    if not eligible:
        raise ValueError(
            "No At Practice mentors need an underfilled-pace email for this season."
        )

    if dry_run:
        sample = eligible[0]
        labels = [row["label"] for row in sample["practices"]]
        return {
            "sent": 0,
            "recipients": len(eligible),
            "subject": UNDERFILLED_PACE_EMAIL_SUBJECT,
            "sample_body": UNDERFILLED_PACE_EMAIL_BODY.format(
                practice_list="\n".join(labels),
                link="https://example.com/underfilled-pace-reply?token=…",
            ),
            "mentors": [serialize_eligible_mentor(entry) for entry in eligible],
        }

    _verify_email_delivery()
    now = timezone.now()

    with transaction.atomic():
        batch = UnderfilledPaceMentorEmailSend.objects.create(
            season_id=season_id,
            sent_at=now,
            recipients_emailed_count=0,
        )
        tokens = []
        label_by_mentor_id = {}
        for entry in eligible:
            mentor = entry["mentor"]
            practice_ids = [row["practice_id"] for row in entry["practices"]]
            label_by_mentor_id[mentor.id] = [row["label"] for row in entry["practices"]]
            tokens.append(
                UnderfilledPaceMentorEmailToken(
                    send=batch,
                    mentor=mentor,
                    sent_at=now,
                    practice_ids=practice_ids,
                )
            )
        UnderfilledPaceMentorEmailToken.objects.bulk_create(tokens)
        tokens = list(
            UnderfilledPaceMentorEmailToken.objects.filter(send=batch).select_related(
                "mentor"
            )
        )

        for token in tokens:
            send_mail(
                subject=UNDERFILLED_PACE_EMAIL_SUBJECT,
                message=render_underfilled_pace_email_body(
                    token, label_by_mentor_id.get(token.mentor_id, [])
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[token.mentor.email],
                fail_silently=False,
            )

        batch.recipients_emailed_count = len(tokens)
        batch.save(update_fields=["recipients_emailed_count", "updated_at"])

    return {
        "sent": len(tokens),
        "recipients": len(tokens),
        "subject": UNDERFILLED_PACE_EMAIL_SUBJECT,
        "send_id": batch.id,
        "sent_at": batch.sent_at.isoformat(),
    }


def build_live_practice_options(token):
    """
    Live options for the reply page from the email snapshot practice ids.

    Excludes practices the mentor is already assigned to. Includes filled (0 slot)
    practices so they can be shown grayed out.
    """
    mentor = token.mentor
    pace = normalize_pace(mentor.pace or "")
    practice_ids = list(token.practice_ids or [])
    if not practice_ids or not pace:
        return []

    practices = {
        p.id: p
        for p in Practice.objects.filter(id__in=practice_ids).order_by("date", "id")
    }
    options = []
    for practice_id in practice_ids:
        practice = practices.get(practice_id)
        if practice is None:
            continue
        if mentor.id in practice.assigned_mentor_ids():
            continue
        slots = slots_remaining_for_pace(practice, pace)
        options.append(
            {
                "practice_id": practice.id,
                "label": format_practice_label(practice),
                "slots_remaining": slots,
                "selectable": slots > 0,
            }
        )
    return options


def mark_token_responded(token, *, response_type, assigned_ids=None, snagged_ids=None):
    token.responded_at = timezone.now()
    token.response_type = response_type
    token.assigned_practice_ids = list(assigned_ids or [])
    token.snagged_practice_ids = list(snagged_ids or [])
    token.save(
        update_fields=[
            "responded_at",
            "response_type",
            "assigned_practice_ids",
            "snagged_practice_ids",
            "updated_at",
        ]
    )


def thank_you_payload(*, snagged_labels=None, assigned_labels=None):
    """Build post-submit messages including optional snagged-slot copy."""
    messages = [THANK_YOU_AFTER_SUBMIT]
    snagged_labels = list(snagged_labels or [])
    assigned_labels = list(assigned_labels or [])
    if snagged_labels:
        snagged_text = ", ".join(snagged_labels)
        if assigned_labels:
            assigned_text = ", ".join(assigned_labels)
            messages.insert(
                0,
                (
                    f"Good news!  someone snagged the slot for {snagged_text} "
                    f"right before you.  You are assigned to {assigned_text}"
                ),
            )
        else:
            messages.insert(
                0,
                (
                    f"Good news!  someone snagged the slot for {snagged_text} "
                    f"right before you."
                ),
            )
    return {
        "completed": True,
        "detail": THANK_YOU_AFTER_SUBMIT,
        "messages": messages,
    }


def submit_unavailable(token):
    if not token.is_open:
        raise ValueError("This link is no longer valid.")
    mark_token_responded(token, response_type=UnderfilledPaceResponseType.UNAVAILABLE)
    return thank_you_payload()


def submit_practice_selections(token, practice_ids):
    """Assign mentor to selected practices that still have slots; handle races."""
    if not token.is_open:
        raise ValueError("This link is no longer valid.")

    requested = []
    seen = set()
    for raw in practice_ids:
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            continue
        if pid in seen:
            continue
        seen.add(pid)
        requested.append(pid)

    if not requested:
        raise ValueError("Select at least one practice, or mark yourself unavailable.")

    allowed_ids = set(token.practice_ids or [])
    for pid in requested:
        if pid not in allowed_ids:
            raise ValueError("One or more selected practices are not available.")

    assigned_ids = []
    snagged_ids = []

    with transaction.atomic():
        locked = (
            UnderfilledPaceMentorEmailToken.objects.select_for_update()
            .select_related("mentor")
            .filter(pk=token.pk)
            .first()
        )
        if locked is None or not locked.is_open:
            raise ValueError("This link is no longer valid.")

        mentor = locked.mentor
        pace = normalize_pace(mentor.pace or "")
        practices = {
            p.id: p
            for p in Practice.objects.select_for_update()
            .filter(id__in=requested)
            .order_by("date", "id")
        }
        for pid in requested:
            practice = practices.get(pid)
            if practice is None:
                snagged_ids.append(pid)
                continue
            if mentor.id in practice.assigned_mentor_ids():
                snagged_ids.append(pid)
                continue
            if slots_remaining_for_pace(practice, pace) <= 0:
                snagged_ids.append(pid)
                continue
            practice.mark_mentor_attending(mentor, pace)
            assigned_ids.append(pid)

        mark_token_responded(
            locked,
            response_type=UnderfilledPaceResponseType.PRACTICES,
            assigned_ids=assigned_ids,
            snagged_ids=snagged_ids,
        )

    practices_for_labels = {
        p.id: format_practice_label(p)
        for p in Practice.objects.filter(id__in=assigned_ids + snagged_ids)
    }
    return thank_you_payload(
        snagged_labels=[
            practices_for_labels[i] for i in snagged_ids if i in practices_for_labels
        ],
        assigned_labels=[
            practices_for_labels[i] for i in assigned_ids if i in practices_for_labels
        ],
    )


def maybe_mark_all_filled_on_open(token, options):
    """
    If the mentor has not responded and every remaining option has 0 slots
    (or there are no selectable practices left), mark responded as all_filled.
    """
    if not token.is_open:
        return False
    has_open_slot = any(row["slots_remaining"] > 0 for row in options)
    if has_open_slot:
        return False
    mark_token_responded(token, response_type=UnderfilledPaceResponseType.ALL_FILLED)
    return True
