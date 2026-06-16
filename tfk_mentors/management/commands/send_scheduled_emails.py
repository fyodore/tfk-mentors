from django.core.management.base import BaseCommand, CommandError

from tfk_mentors.email_sending import due_scheduled_emails, send_scheduled_email
from tfk_mentors.models import ScheduledEmail
from tfk_mentors.practice_reminder import (
    due_practice_reminder_emails,
    send_practice_reminder,
)


class Command(BaseCommand):
    help = (
        "Send scheduled mentor emails and practice reminder emails "
        "whose send time has passed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be sent without emailing or updating the database.",
        )
        parser.add_argument(
            "--id",
            type=int,
            help="Send a specific ScheduledEmail id (ignores send time unless forced).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="With --id, send even if not yet due or already marked sent.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        email_id = options.get("id")
        force = options["force"]

        if email_id is not None:
            try:
                rows = [
                    ScheduledEmail.objects.select_related("recipient_season")
                    .prefetch_related("practices")
                    .get(pk=email_id)
                ]
            except ScheduledEmail.DoesNotExist as exc:
                raise CommandError(f"ScheduledEmail {email_id} not found.") from exc
            if rows[0].task_completed_at and not force:
                raise CommandError(
                    f"ScheduledEmail {email_id} was already sent. Use --force to resend."
                )
            reminder_rows = []
        else:
            rows = list(due_scheduled_emails())
            reminder_rows = list(due_practice_reminder_emails())

        if not rows and not reminder_rows:
            self.stdout.write("No scheduled emails due.")
            return

        for scheduled in rows:
            label = (
                f"ScheduledEmail {scheduled.pk} "
                f"(due {scheduled.scheduled_send_at.isoformat()})"
            )
            try:
                result = send_scheduled_email(scheduled, dry_run=dry_run)
            except Exception as exc:
                raise CommandError(f"{label}: {exc}") from exc

            if dry_run:
                self.stdout.write(
                    f"DRY RUN {label}: would email {result['recipients']} mentor(s) "
                    f"with subject {result['subject']!r}"
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Sent {label} to {result['sent']} mentor(s)."
                    )
                )

        for reminder in reminder_rows:
            label = (
                f"PracticeReminderEmail {reminder.pk} "
                f"(due {reminder.scheduled_send_at.isoformat()})"
            )
            try:
                result = send_practice_reminder(reminder, dry_run=dry_run)
            except Exception as exc:
                raise CommandError(f"{label}: {exc}") from exc

            if dry_run:
                self.stdout.write(
                    f"DRY RUN {label}: would email {result['recipients']} recipient(s) "
                    f"with subject {result['subject']!r}"
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Sent {label} to {result['sent']} recipient(s)."
                    )
                )
