"""Tests for the send_scheduled_emails management command."""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from tfk_mentors.models import (
    Practice,
    PracticeReminderEmail,
    PracticeReminderKind,
    ScheduledEmail,
    Season,
)

COMMAND = "send_scheduled_emails"
MODULE = "tfk_mentors.management.commands.send_scheduled_emails"


class SendScheduledEmailsCommandTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2026)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=5),
            season=self.season,
        )
        self.due_email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() - timedelta(minutes=5),
            body_text="Hello",
            recipient_season=self.season,
        )
        self.future_email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() + timedelta(days=1),
            body_text="Later",
            recipient_season=self.season,
        )
        self.due_reminder = PracticeReminderEmail.objects.create(
            season=self.season,
            anchor_practice=self.practice,
            practice_one=self.practice,
            kind=PracticeReminderKind.BEFORE_FIRST,
            subject="Reminder subject",
            body_text="Reminder body",
            scheduled_send_at=timezone.now() - timedelta(minutes=5),
        )
        self.future_reminder = PracticeReminderEmail.objects.create(
            season=self.season,
            anchor_practice=self.practice,
            practice_one=self.practice,
            kind=PracticeReminderKind.AFTER_PRACTICE,
            subject="Later reminder",
            body_text="Later reminder body",
            scheduled_send_at=timezone.now() + timedelta(days=1),
        )

    def _run(self, *args, **kwargs):
        out = StringIO()
        call_command(COMMAND, *args, stdout=out, **kwargs)
        return out.getvalue()

    def test_no_scheduled_emails_due_reports_message(self):
        ScheduledEmail.objects.all().delete()
        PracticeReminderEmail.objects.all().delete()

        output = self._run()

        self.assertIn("No scheduled emails due.", output)

    @patch(f"{MODULE}.send_practice_reminder")
    @patch(f"{MODULE}.send_scheduled_email")
    def test_dry_run_reports_counts_without_sending(self, mock_send_email, mock_send_reminder):
        mock_send_email.return_value = {"sent": 0, "recipients": 3, "subject": "Subj A"}
        mock_send_reminder.return_value = {
            "recipients": 2,
            "subject": "Subj B",
            "sample_body": "body",
        }

        output = self._run("--dry-run")

        mock_send_email.assert_called_once_with(self.due_email, dry_run=True)
        mock_send_reminder.assert_called_once_with(self.due_reminder, dry_run=True)
        self.assertIn("DRY RUN", output)
        self.assertIn("3 mentor(s)", output)
        self.assertIn("Subj A", output)
        self.assertIn("2 recipient(s)", output)
        self.assertIn("Subj B", output)

        self.due_email.refresh_from_db()
        self.due_reminder.refresh_from_db()
        self.assertIsNone(self.due_email.task_completed_at)
        self.assertIsNone(self.due_reminder.task_completed_at)

    @patch(f"{MODULE}.send_practice_reminder")
    @patch(f"{MODULE}.send_scheduled_email")
    def test_default_run_sends_scheduled_and_reminder_due_rows(
        self, mock_send_email, mock_send_reminder
    ):
        mock_send_email.return_value = {"sent": 3, "recipients": 3, "subject": "Subj A"}
        mock_send_reminder.return_value = {"sent": 2, "recipients": 2}

        output = self._run()

        mock_send_email.assert_called_once_with(self.due_email, dry_run=False)
        mock_send_reminder.assert_called_once_with(self.due_reminder, dry_run=False)
        self.assertIn("Sent ScheduledEmail", output)
        self.assertIn("3 mentor(s)", output)
        self.assertIn("Sent PracticeReminderEmail", output)
        self.assertIn("2 recipient(s)", output)

    @patch(f"{MODULE}.send_practice_reminder")
    @patch(f"{MODULE}.send_scheduled_email")
    def test_id_option_ignores_due_reminders(self, mock_send_email, mock_send_reminder):
        mock_send_email.return_value = {"sent": 1, "recipients": 1, "subject": "Subj"}

        output = self._run("--id", self.due_email.id)

        mock_send_email.assert_called_once_with(self.due_email, dry_run=False)
        mock_send_reminder.assert_not_called()
        self.assertIn("Sent ScheduledEmail", output)

    def test_id_option_missing_raises_command_error(self):
        missing_id = self.due_email.id + self.future_email.id + 1000
        with self.assertRaises(CommandError) as ctx:
            self._run("--id", missing_id)
        self.assertIn(f"ScheduledEmail {missing_id} not found.", str(ctx.exception))

    def test_id_option_already_sent_without_force_raises(self):
        self.due_email.task_completed_at = timezone.now()
        self.due_email.save(update_fields=["task_completed_at"])

        with self.assertRaises(CommandError) as ctx:
            self._run("--id", self.due_email.id)
        self.assertIn("already sent", str(ctx.exception))
        self.assertIn("--force", str(ctx.exception))

    @patch(f"{MODULE}.send_scheduled_email")
    def test_id_option_already_sent_with_force_resends(self, mock_send_email):
        self.due_email.task_completed_at = timezone.now()
        self.due_email.save(update_fields=["task_completed_at"])
        mock_send_email.return_value = {"sent": 1, "recipients": 1, "subject": "Subj"}

        output = self._run("--id", self.due_email.id, "--force")

        mock_send_email.assert_called_once_with(self.due_email, dry_run=False)
        self.assertIn("Sent ScheduledEmail", output)

    @patch(f"{MODULE}.send_scheduled_email")
    def test_id_option_not_yet_due_with_force_sends_anyway(self, mock_send_email):
        mock_send_email.return_value = {"sent": 1, "recipients": 1, "subject": "Subj"}

        output = self._run("--id", self.future_email.id, "--force")

        mock_send_email.assert_called_once_with(self.future_email, dry_run=False)
        self.assertIn("Sent ScheduledEmail", output)

    @patch(f"{MODULE}.send_scheduled_email", side_effect=ValueError("no recipients"))
    def test_scheduled_email_error_wrapped_in_command_error(self, mock_send_email):
        with self.assertRaises(CommandError) as ctx:
            self._run()
        self.assertIn(f"ScheduledEmail {self.due_email.pk}", str(ctx.exception))
        self.assertIn("no recipients", str(ctx.exception))

    @patch(f"{MODULE}.send_scheduled_email")
    @patch(f"{MODULE}.send_practice_reminder", side_effect=ValueError("no recipients"))
    def test_practice_reminder_error_wrapped_in_command_error(
        self, mock_send_reminder, mock_send_email
    ):
        mock_send_email.return_value = {"sent": 1, "recipients": 1, "subject": "Subj"}

        with self.assertRaises(CommandError) as ctx:
            self._run()
        self.assertIn(f"PracticeReminderEmail {self.due_reminder.pk}", str(ctx.exception))
        self.assertIn("no recipients", str(ctx.exception))
