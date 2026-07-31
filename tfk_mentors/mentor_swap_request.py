"""Public mentor-directory swap requests: create, approve, reject, notify."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .email_sending import _verify_email_delivery
from .models import (
    Mentor,
    MentorSwapRequest,
    MentorSwapRequestStatus,
    PaceTypes,
    normalize_pace,
)
from .practice_reminder import format_practice_date
from .practice_swap_notification import (
    mentor_display_name,
    practice_has_started,
    practice_last_reminder_already_sent,
    send_mentor_swap_coach_notification,
    send_mentor_swap_confirmations,
)

SWAP_REQUEST_REJECT_NOTIFY_EMAIL = "fyodore@gmail.com"


def mentor_public_row(mentor, *, pace=None):
    return {
        "mentor_id": mentor.id,
        "first_name": mentor.first_name,
        "last_name": mentor.last_name,
        "pace": normalize_pace(pace if pace is not None else (mentor.pace or "")),
        "type": mentor.type,
    }


def build_public_practice_swap_options(practice):
    """Attending mentors and eligible incoming mentors for a public swap request."""
    practice.sync_mentor_assignments_from_replies()
    attending_ids = set()
    attending = []
    for mentor, pace, _reply, _assignment in practice.attending_mentor_roster_entries():
        attending_ids.add(mentor.id)
        attending.append(mentor_public_row(mentor, pace=pace))

    valid_paces = {choice.value for choice in PaceTypes}
    incoming = []
    for mentor in (
        Mentor.objects.filter(seasons=practice.season_id)
        .exclude(id__in=attending_ids)
        .order_by("last_name", "first_name", "id")
    ):
        pace = normalize_pace(mentor.pace or "")
        if not pace or pace not in valid_paces:
            continue
        incoming.append(mentor_public_row(mentor, pace=pace))

    incoming.sort(
        key=lambda row: (
            {choice.value: index for index, choice in enumerate(PaceTypes)}.get(
                row["pace"], 99
            ),
            row["last_name"] or "",
            row["first_name"] or "",
        )
    )

    return {
        "practice_id": practice.id,
        "date": practice.date,
        "nyrr_race": practice.nyrr_race or "",
        "season_year": practice.season.year if practice.season_id else None,
        "attending_mentors": attending,
        "incoming_mentors": incoming,
    }


def validate_swap_request_pair(practice, outgoing, incoming):
    if incoming.id == outgoing.id:
        raise ValidationError("Choose a different mentor for the swap.")
    if outgoing.id not in practice.assigned_mentor_ids():
        raise ValidationError("Outgoing mentor is not assigned to this practice.")
    if incoming.id in practice.assigned_mentor_ids():
        raise ValidationError("Replacement mentor is already assigned to this practice.")
    if not incoming.seasons.filter(id=practice.season_id).exists():
        raise ValidationError(
            "Replacement mentor must belong to the practice season."
        )
    pace = normalize_pace(incoming.pace or "")
    if not pace or pace not in {choice.value for choice in PaceTypes}:
        raise ValidationError("Replacement mentor must have a pace on file.")
    if not (incoming.email or "").strip():
        raise ValidationError(
            "Replacement mentor needs an email address to receive the swap request."
        )
    if practice_has_started(practice):
        raise ValidationError("This practice has already started.")
    if not practice.show_to_mentors:
        raise ValidationError("Practice not found.")


def swap_request_email_subject():
    return "Mentor Swap Request Approval"


def swap_request_email_body(request_row: MentorSwapRequest):
    practice = request_row.practice
    practice_when = format_practice_date(practice)
    race = (practice.nyrr_race or "").strip()
    practice_line = (
        f"{practice_when} · NYRR Race: {race}" if race else practice_when
    )
    return (
        f"A mentor swap has been requested for the TFK practice on {practice_line}.\n"
        f"\n"
        f"Original mentor: {mentor_display_name(request_row.outgoing_mentor)}\n"
        f"Requested replacement mentor: {mentor_display_name(request_row.incoming_mentor)}\n"
        f"\n"
        f"Please choose one of the options below:\n"
        f"\n"
        f"Approve Swap:\n"
        f"{request_row.approve_absolute_url()}\n"
        f"\n"
        f"Reject Swap:\n"
        f"{request_row.reject_absolute_url()}\n"
    )


def send_swap_request_email(request_row: MentorSwapRequest, *, dry_run=False):
    email = (request_row.incoming_mentor.email or "").strip()
    subject = swap_request_email_subject()
    body = swap_request_email_body(request_row)
    if dry_run or not email:
        return {
            "sent": 0,
            "recipients": 1 if email else 0,
            "subject": subject,
            "skipped": not email,
        }

    _verify_email_delivery()
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
    return {
        "sent": 1,
        "recipients": 1,
        "subject": subject,
        "skipped": False,
    }


def create_mentor_swap_request(practice, outgoing, incoming):
    practice.sync_mentor_assignments_from_replies()
    validate_swap_request_pair(practice, outgoing, incoming)
    outgoing_pace = ""
    for mentor, pace, _reply, _assignment in practice.attending_mentor_roster_entries():
        if mentor.id == outgoing.id:
            outgoing_pace = pace
            break
    if not outgoing_pace:
        outgoing_pace = normalize_pace(outgoing.pace or "")
    incoming_pace = normalize_pace(incoming.pace or "")
    with transaction.atomic():
        request_row = MentorSwapRequest.objects.create(
            practice=practice,
            outgoing_mentor=outgoing,
            incoming_mentor=incoming,
            status=MentorSwapRequestStatus.PENDING,
            outgoing_pace=outgoing_pace,
            incoming_pace=incoming_pace,
        )
    try:
        email_result = send_swap_request_email(request_row)
    except Exception as exc:
        email_result = {
            "sent": 0,
            "recipients": 1,
            "subject": swap_request_email_subject(),
            "skipped": False,
            "error": str(exc),
            "approve_url": request_row.approve_absolute_url(),
            "reject_url": request_row.reject_absolute_url(),
        }
    return request_row, email_result


def approve_mentor_swap_request(request_row: MentorSwapRequest):
    if request_row.status == MentorSwapRequestStatus.APPROVED:
        return {
            "already_decided": True,
            "status": request_row.status,
            "message": "This swap request was already approved.",
        }
    if request_row.status == MentorSwapRequestStatus.REJECTED:
        raise ValidationError("This swap request was already rejected.")

    practice = request_row.practice
    outgoing = request_row.outgoing_mentor
    incoming = request_row.incoming_mentor
    practice.sync_mentor_assignments_from_replies()
    validate_swap_request_pair(practice, outgoing, incoming)

    with transaction.atomic():
        result = practice.swap_assigned_mentor(outgoing, incoming)
        pace = normalize_pace(getattr(result, "pace", "") or incoming.pace or "")
        request_row.status = MentorSwapRequestStatus.APPROVED
        request_row.decided_at = timezone.now()
        request_row.incoming_pace = pace or request_row.incoming_pace
        if not request_row.outgoing_pace:
            request_row.outgoing_pace = normalize_pace(outgoing.pace or "")
        request_row.save(
            update_fields=[
                "status",
                "decided_at",
                "outgoing_pace",
                "incoming_pace",
                "updated_at",
            ]
        )

    mentor_confirmations = None
    coach_notification = None
    if not practice_has_started(practice):
        mentor_confirmations = send_mentor_swap_confirmations(
            practice,
            outgoing,
            incoming,
        )
        if practice_last_reminder_already_sent(practice):
            coach_notification = send_mentor_swap_coach_notification(
                practice,
                outgoing,
                incoming,
                pace,
            )

    return {
        "already_decided": False,
        "status": request_row.status,
        "message": (
            "The mentor swap was successful.  You both should receive an email "
            "with a confirmation."
        ),
        "mentor_confirmations": mentor_confirmations,
        "coach_notification": coach_notification,
        "practice_id": practice.id,
        "outgoing_mentor": mentor_public_row(
            outgoing, pace=request_row.outgoing_pace
        ),
        "incoming_mentor": mentor_public_row(incoming, pace=pace),
    }


def rejected_swap_email_subject():
    return "Rejected Mentor Swap"


def rejected_swap_email_body(request_row: MentorSwapRequest):
    practice = request_row.practice
    practice_when = format_practice_date(practice)
    comments = (request_row.reject_comments or "").strip() or "(none)"
    return (
        f"A mentor swap request was rejected.\n"
        f"\n"
        f"Practice: {practice_when}\n"
        f"Original mentor: {mentor_display_name(request_row.outgoing_mentor)}\n"
        f"Requested replacement: {mentor_display_name(request_row.incoming_mentor)}\n"
        f"\n"
        f"Comments:\n{comments}\n"
        f"\n"
        f"Open in Reports (Mentor Swap):\n"
        f"{request_row.reports_absolute_url()}\n"
    )


def send_rejected_swap_email(request_row: MentorSwapRequest, *, dry_run=False):
    subject = rejected_swap_email_subject()
    body = rejected_swap_email_body(request_row)
    if dry_run:
        return {"sent": 0, "recipients": 1, "subject": subject, "skipped": False}

    _verify_email_delivery()
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[SWAP_REQUEST_REJECT_NOTIFY_EMAIL],
        fail_silently=False,
    )
    return {
        "sent": 1,
        "recipients": 1,
        "subject": subject,
        "skipped": False,
    }


def reject_mentor_swap_request(request_row: MentorSwapRequest, comments: str):
    if request_row.status == MentorSwapRequestStatus.REJECTED:
        return {
            "already_decided": True,
            "status": request_row.status,
            "message": "This swap request was already rejected.",
        }
    if request_row.status == MentorSwapRequestStatus.APPROVED:
        raise ValidationError("This swap request was already approved.")

    request_row.status = MentorSwapRequestStatus.REJECTED
    request_row.reject_comments = (comments or "").strip()
    request_row.decided_at = timezone.now()
    request_row.save(
        update_fields=["status", "reject_comments", "decided_at", "updated_at"]
    )
    try:
        email_result = send_rejected_swap_email(request_row)
    except Exception as exc:
        email_result = {
            "sent": 0,
            "recipients": 1,
            "subject": rejected_swap_email_subject(),
            "skipped": False,
            "error": str(exc),
        }
    return {
        "already_decided": False,
        "status": request_row.status,
        "message": "Your rejection was submitted. Thank you.",
        "email": email_result,
        "reports_url": request_row.reports_absolute_url(),
    }


def mentor_swap_request_summary(request_row: MentorSwapRequest):
    practice = request_row.practice
    return {
        "id": request_row.id,
        "status": request_row.status,
        "token": str(request_row.token),
        "practice_id": practice.id,
        "practice_date": practice.date,
        "nyrr_race": practice.nyrr_race or "",
        "season_year": practice.season.year if practice.season_id else None,
        "outgoing_mentor": mentor_public_row(
            request_row.outgoing_mentor, pace=request_row.outgoing_pace
        ),
        "incoming_mentor": mentor_public_row(
            request_row.incoming_mentor, pace=request_row.incoming_pace
        ),
        "reject_comments": request_row.reject_comments or "",
        "decided_at": request_row.decided_at,
        "created_at": request_row.created_at,
    }


def build_mentor_swap_report(*, season_id=None):
    qs = MentorSwapRequest.objects.select_related(
        "practice",
        "practice__season",
        "outgoing_mentor",
        "incoming_mentor",
    ).order_by("-decided_at", "-created_at", "-id")
    if season_id is not None:
        qs = qs.filter(practice__season_id=season_id)

    approved = []
    rejected = []
    for row in qs:
        if row.status == MentorSwapRequestStatus.PENDING:
            continue
        summary = mentor_swap_request_summary(row)
        if row.status == MentorSwapRequestStatus.APPROVED:
            approved.append(summary)
        elif row.status == MentorSwapRequestStatus.REJECTED:
            rejected.append(summary)

    return {"approved": approved, "rejected": rejected}
