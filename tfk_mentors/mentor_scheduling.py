"""First-run mentor scheduling from practice email replies."""

from collections import defaultdict
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction

from .models import (
    Mentor,
    MentorTypes,
    PACE_SORT,
    Practice,
    PracticeAttendanceReply,
    ScheduledEmailMentorPracticeReply,
    normalize_pace,
)

ATTENDING_VALUES = frozenset(
    {
        PracticeAttendanceReply.ATTENDING,
        PracticeAttendanceReply.FIRST_HALF,
        PracticeAttendanceReply.SECOND_HALF,
    }
)

MAX_MENTORS_PER_PACE = 4
MAX_PRACTICES_PER_MONTH = 2


def _display_timezone():
    return ZoneInfo(settings.TIME_ZONE)


def _practice_month_key(practice):
    local = practice.date.astimezone(_display_timezone())
    return (local.year, local.month)


def _mentor_row(mentor, *, pace, selection_count, attendance=PracticeAttendanceReply.ATTENDING):
    return {
        "mentor_id": mentor.id,
        "first_name": mentor.first_name,
        "last_name": mentor.last_name,
        "email": mentor.email,
        "pace": pace,
        "mentor_type": mentor.type,
        "selection_count": selection_count,
        "attendance": attendance,
    }


def _serialize_mentor_rows(rows):
    return sorted(
        rows,
        key=lambda row: (
            PACE_SORT.get(row["pace"], 99),
            row["last_name"],
            row["first_name"],
        ),
    )


def _latest_attending_replies_for_practices(practice_ids):
    """Latest attending reply per (mentor, practice) among selected practices."""
    if not practice_ids:
        return []
    latest = {}
    queryset = (
        ScheduledEmailMentorPracticeReply.objects.filter(
            practice_id__in=practice_ids,
            attendance__in=ATTENDING_VALUES,
        )
        .select_related("mentor", "practice")
        .order_by("practice_id", "mentor_id", "-updated_at")
    )
    for reply in queryset:
        key = (reply.mentor_id, reply.practice_id)
        if key not in latest:
            latest[key] = reply
    return list(latest.values())


def compute_mentor_schedule(practices):
    """
    Build a first-run assignment plan from mentor email replies.

  Rules:
    - At Practice mentors only are assigned; Remote mentors are listed separately.
    - Mentors with fewer practice selections are processed first.
    - Each mentor receives up to two assigned practices per calendar month.
    - Each practice allows at most four assigned mentors per pace group.
    - Unassigned selections move to available when the pace group still has room.
    """
    practices = sorted(practices, key=lambda p: (p.date, p.id))
    practice_by_id = {practice.id: practice for practice in practices}
    practice_ids = list(practice_by_id.keys())

    replies = _latest_attending_replies_for_practices(practice_ids)

    selections_by_mentor = defaultdict(list)
    remote_by_mentor = {}
    for reply in replies:
        mentor = reply.mentor
        pace = normalize_pace(reply.pace or mentor.pace or "")
        if not pace:
            continue
        if mentor.type == MentorTypes.REMOTE:
            existing = remote_by_mentor.get(mentor.id)
            if existing is None:
                remote_by_mentor[mentor.id] = {
                    "mentor": mentor,
                    "practices": [],
                }
            remote_by_mentor[mentor.id]["practices"].append(
                {
                    "practice_id": reply.practice_id,
                    "date": practice_by_id[reply.practice_id].date.isoformat(),
                    "nyrr_race": practice_by_id[reply.practice_id].nyrr_race or "",
                    "pace": pace,
                    "attendance": reply.attendance,
                }
            )
            continue
        if mentor.type != MentorTypes.PRACTICE:
            continue
        selections_by_mentor[mentor.id].append(
            {
                "practice_id": reply.practice_id,
                "pace": pace,
                "attendance": reply.attendance,
            }
        )

    mentor_ids = list(selections_by_mentor.keys())
    mentors_by_id = Mentor.objects.in_bulk(mentor_ids)

    mentors_sorted = sorted(
        mentor_ids,
        key=lambda mid: (
            len(selections_by_mentor[mid]),
            mentors_by_id[mid].last_name,
            mentors_by_id[mid].first_name,
        ),
    )

    assigned_by_practice_pace = defaultdict(int)
    assigned_count_by_mentor_month = defaultdict(int)
    assignments = defaultdict(list)
    available = defaultdict(list)
    paces_with_interest = defaultdict(set)
    for mentor_id, mentor_selections in selections_by_mentor.items():
        for selection in mentor_selections:
            paces_with_interest[selection["practice_id"]].add(selection["pace"])
    skipped_mentors = []

    for mentor_id in mentors_sorted:
        mentor = mentors_by_id[mentor_id]
        mentor_selections = sorted(
            selections_by_mentor[mentor_id],
            key=lambda sel: (
                practice_by_id[sel["practice_id"]].date,
                sel["practice_id"],
            ),
        )
        for selection in mentor_selections:
            practice = practice_by_id[selection["practice_id"]]
            month_key = _practice_month_key(practice)
            pace = selection["pace"]
            pace_key = (selection["practice_id"], pace)

            if assigned_count_by_mentor_month[(mentor_id, month_key)] >= MAX_PRACTICES_PER_MONTH:
                continue
            if assigned_by_practice_pace[pace_key] >= MAX_MENTORS_PER_PACE:
                continue

            assigned_by_practice_pace[pace_key] += 1
            assigned_count_by_mentor_month[(mentor_id, month_key)] += 1
            assignments[selection["practice_id"]].append(
                _mentor_row(
                    mentor,
                    pace=pace,
                    selection_count=len(mentor_selections),
                    attendance=selection["attendance"],
                )
            )

    for mentor_id in mentors_sorted:
        mentor = mentors_by_id[mentor_id]
        mentor_selections = selections_by_mentor[mentor_id]
        assigned_practice_ids = {
            practice_id
            for practice_id, rows in assignments.items()
            for row in rows
            if row["mentor_id"] == mentor_id
        }
        seen_available = set()
        for selection in mentor_selections:
            if selection["practice_id"] in assigned_practice_ids:
                continue
            avail_key = (mentor_id, selection["practice_id"])
            if avail_key in seen_available:
                continue
            pace_key = (selection["practice_id"], selection["pace"])
            if assigned_by_practice_pace[pace_key] >= MAX_MENTORS_PER_PACE:
                continue
            seen_available.add(avail_key)
            available[selection["practice_id"]].append(
                _mentor_row(
                    mentor,
                    pace=selection["pace"],
                    selection_count=len(mentor_selections),
                    attendance=PracticeAttendanceReply.AVAILABLE,
                )
            )

    practice_rows = []
    total_assigned = 0
    total_available = 0
    for practice in practices:
        assignments_by_pace = defaultdict(list)
        available_by_pace = defaultdict(list)
        for row in assignments.get(practice.id, []):
            assignments_by_pace[row["pace"]].append(row)
            total_assigned += 1
        for row in available.get(practice.id, []):
            available_by_pace[row["pace"]].append(row)
            total_available += 1
        underfilled_pace_groups = []
        for pace in sorted(
            paces_with_interest.get(practice.id, []),
            key=lambda value: PACE_SORT.get(value, 99),
        ):
            assigned_count = len(assignments_by_pace.get(pace, []))
            if assigned_count < MAX_MENTORS_PER_PACE:
                underfilled_pace_groups.append(
                    {
                        "pace": pace,
                        "assigned_count": assigned_count,
                        "slots_remaining": MAX_MENTORS_PER_PACE - assigned_count,
                    }
                )
        practice_rows.append(
            {
                "practice_id": practice.id,
                "date": practice.date.isoformat(),
                "nyrr_race": practice.nyrr_race or "",
                "assignments_by_pace": {
                    pace: _serialize_mentor_rows(rows)
                    for pace, rows in assignments_by_pace.items()
                },
                "available_by_pace": {
                    pace: _serialize_mentor_rows(rows)
                    for pace, rows in available_by_pace.items()
                },
                "underfilled_pace_groups": underfilled_pace_groups,
            }
        )

    remote_mentors = []
    for entry in remote_by_mentor.values():
        mentor = entry["mentor"]
        practices_list = sorted(
            entry["practices"],
            key=lambda row: (row["date"], row["practice_id"]),
        )
        remote_mentors.append(
            {
                "mentor_id": mentor.id,
                "first_name": mentor.first_name,
                "last_name": mentor.last_name,
                "email": mentor.email,
                "pace": mentor.pace or "",
                "mentor_type": mentor.type,
                "practices": practices_list,
            }
        )
    remote_mentors.sort(
        key=lambda row: (row["last_name"], row["first_name"], row["mentor_id"])
    )

    underfilled_practices = [
        {
            "practice_id": row["practice_id"],
            "date": row["date"],
            "nyrr_race": row["nyrr_race"],
            "underfilled_pace_groups": row["underfilled_pace_groups"],
        }
        for row in practice_rows
        if row["underfilled_pace_groups"]
    ]

    return {
        "practices": practice_rows,
        "underfilled_practices": underfilled_practices,
        "remote_mentors": remote_mentors,
        "summary": {
            "mentors_considered": len(mentors_sorted),
            "mentors_assigned": len(
                {
                    row["mentor_id"]
                    for rows in assignments.values()
                    for row in rows
                }
            ),
            "assignment_rows": total_assigned,
            "available_rows": total_available,
            "remote_mentors": len(remote_mentors),
            "underfilled_practice_count": len(underfilled_practices),
            "max_per_pace": MAX_MENTORS_PER_PACE,
            "max_per_month": MAX_PRACTICES_PER_MONTH,
        },
        "skipped_mentors": skipped_mentors,
    }


def apply_mentor_schedule(practices, schedule):
    """Apply computed assignments and available lists to practices."""
    practice_by_id = {practice.id: practice for practice in practices}
    applied = {"assigned": 0, "available": 0, "errors": []}

    with transaction.atomic():
        for practice_row in schedule["practices"]:
            practice = practice_by_id.get(practice_row["practice_id"])
            if practice is None:
                continue
            for pace_rows in practice_row["assignments_by_pace"].values():
                for row in pace_rows:
                    mentor = Mentor.objects.get(pk=row["mentor_id"])
                    try:
                        practice.mark_mentor_attending(mentor, row["pace"])
                        applied["assigned"] += 1
                    except Exception as exc:
                        applied["errors"].append(
                            {
                                "mentor_id": row["mentor_id"],
                                "practice_id": practice.id,
                                "action": "assign",
                                "detail": str(exc),
                            }
                        )
            for pace_rows in practice_row["available_by_pace"].values():
                for row in pace_rows:
                    mentor = Mentor.objects.get(pk=row["mentor_id"])
                    try:
                        practice.mark_mentor_available(mentor, pace=row["pace"])
                        applied["available"] += 1
                    except Exception as exc:
                        applied["errors"].append(
                            {
                                "mentor_id": row["mentor_id"],
                                "practice_id": practice.id,
                                "action": "available",
                                "detail": str(exc),
                            }
                        )

    return applied
