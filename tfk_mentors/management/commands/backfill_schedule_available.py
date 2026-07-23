"""Backfill available status for mentors missed by an older scheduler."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from tfk_mentors.mentor_scheduling import compute_mentor_schedule
from tfk_mentors.models import Mentor, Practice


class Command(BaseCommand):
    help = (
        "Mark mentors as available when they replied for a practice but were not "
        "assigned (pace group full or monthly limit). Use after an older schedule "
        "apply that skipped those available moves."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without updating the database.",
        )
        parser.add_argument(
            "--practice-id",
            type=int,
            action="append",
            dest="practice_ids",
            help="Limit to one or more practice ids (repeatable).",
        )
        parser.add_argument(
            "--season-id",
            type=int,
            help="Limit to practices in this season.",
        )
        parser.add_argument(
            "--upcoming-only",
            action="store_true",
            help="Only practices with date >= now.",
        )
        parser.add_argument(
            "--include-open",
            action="store_true",
            help=(
                "Include practices that do not have mentor selection closed. "
                "Default is only practices already scheduled (selection closed)."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        practice_ids = options.get("practice_ids") or []
        season_id = options.get("season_id")
        upcoming_only = options["upcoming_only"]
        include_open = options["include_open"]

        qs = Practice.objects.select_related("season").order_by("date", "id")
        if practice_ids:
            qs = qs.filter(pk__in=practice_ids)
        elif not include_open:
            qs = qs.filter(mentor_selection_closed_at__isnull=False)
        if season_id is not None:
            qs = qs.filter(season_id=season_id)
        if upcoming_only:
            qs = qs.filter(date__gte=timezone.now())

        practices = list(qs)
        if practice_ids:
            found = {practice.id for practice in practices}
            missing = [pid for pid in practice_ids if pid not in found]
            if missing:
                raise CommandError(f"Practice not found: {missing[0]}.")

        if not practices:
            self.stdout.write("No matching practices.")
            return

        schedule = compute_mentor_schedule(practices)
        practice_by_id = {practice.id: practice for practice in practices}
        would_move = []
        errors = []

        for practice_row in schedule["practices"]:
            practice = practice_by_id.get(practice_row["practice_id"])
            if practice is None:
                continue
            already_available = {
                reply.mentor_id for reply in practice.latest_available_mentor_replies()
            }
            for pace, rows in (practice_row.get("available_by_pace") or {}).items():
                for row in rows:
                    mentor_id = row["mentor_id"]
                    if mentor_id in already_available:
                        continue
                    would_move.append(
                        {
                            "practice": practice,
                            "mentor_id": mentor_id,
                            "pace": row.get("pace") or pace,
                            "first_name": row.get("first_name") or "",
                            "last_name": row.get("last_name") or "",
                        }
                    )

        if not would_move:
            self.stdout.write(
                "No mentors need to be moved to available for the selected practices."
            )
            return

        self.stdout.write(
            f"{'Would mark' if dry_run else 'Marking'} {len(would_move)} mentor "
            f"practice selection(s) as available:"
        )
        for entry in would_move:
            practice = entry["practice"]
            name = f"{entry['first_name']} {entry['last_name']}".strip() or "—"
            when = practice.date.isoformat() if practice.date else "—"
            self.stdout.write(
                f"  practice {practice.id} ({when}) · mentor {entry['mentor_id']} "
                f"{name} · pace {entry['pace']}"
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run only — no changes written."))
            return

        moved = 0
        with transaction.atomic():
            mentors = Mentor.objects.in_bulk(
                {entry["mentor_id"] for entry in would_move}
            )
            by_practice = {}
            for entry in would_move:
                by_practice.setdefault(entry["practice"].id, []).append(entry)

            for practice_id, entries in by_practice.items():
                practice = practice_by_id[practice_id]
                for entry in entries:
                    mentor = mentors.get(entry["mentor_id"])
                    if mentor is None:
                        errors.append(
                            {
                                "practice_id": practice_id,
                                "mentor_id": entry["mentor_id"],
                                "detail": "Mentor not found.",
                            }
                        )
                        continue
                    try:
                        practice.mark_mentor_available(
                            mentor, pace=entry["pace"], sync=False
                        )
                        moved += 1
                    except Exception as exc:
                        errors.append(
                            {
                                "practice_id": practice_id,
                                "mentor_id": entry["mentor_id"],
                                "detail": str(exc),
                            }
                        )
                practice.sync_mentor_assignments_from_replies()

        self.stdout.write(
            self.style.SUCCESS(f"Marked {moved} mentor selection(s) as available.")
        )
        if errors:
            self.stdout.write(self.style.ERROR(f"{len(errors)} error(s):"))
            for err in errors:
                self.stdout.write(
                    f"  practice {err['practice_id']} · mentor {err['mentor_id']}: "
                    f"{err['detail']}"
                )
            raise CommandError("Finished with errors; see above.")
