"""Coverage for email_sending.py branches not exercised by feature tests."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from tfk_mentors.email_sending import (
    _verify_email_delivery,
    default_subject,
    send_reply_reminders,
    send_scheduled_email,
)
from tfk_mentors.models import (
    Mentor,
    MentorTypes,
    ScheduledEmail,
    Season,
)


class DefaultSubjectTests(TestCase):
    def test_falls_back_when_year_unresolved(self):
        email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="Hi",
        )
        self.assertEqual(default_subject(email), "TFK Mentors — practice confirmation")


class SendScheduledEmailEdgeCaseTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2026)

    def test_raises_when_no_recipients(self):
        email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="Hi",
            recipient_season=self.season,
        )
        with self.assertRaises(ValueError):
            send_scheduled_email(email)

    def test_dry_run_returns_without_sending_or_marking_complete(self):
        mentor = Mentor.objects.create(
            first_name="Dry",
            last_name="Run",
            email="dryrun@example.com",
            cell_phone="555-0001",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        mentor.seasons.add(self.season)
        email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="Hi {{ first_name }}",
            recipient_season=self.season,
        )
        result = send_scheduled_email(email, dry_run=True)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["recipients"], 1)
        self.assertIsNone(email.task_completed_at)


class VerifyEmailDeliveryTests(TestCase):
    @patch("tfk_mentors.email_sending.verify_gmail_api_access")
    @patch("tfk_mentors.email_sending.gmail_oauth_configured", return_value=True)
    @override_settings(
        EMAIL_BACKEND="tfk_mentors.email_backends.GmailApiEmailBackend"
    )
    def test_uses_gmail_api_verification_when_configured(
        self, _mock_configured, mock_verify
    ):
        _verify_email_delivery()
        mock_verify.assert_called_once()

    @patch("tfk_mentors.email_sending.get_connection")
    def test_oserror_wrapped_in_connection_error_with_context(
        self, mock_get_connection
    ):
        mock_get_connection.return_value.open.side_effect = OSError(
            "network unreachable"
        )
        with self.assertRaises(ConnectionError) as ctx:
            _verify_email_delivery()
        self.assertIn("Cannot reach SMTP server", str(ctx.exception))
        self.assertIn("Original error:", str(ctx.exception))

    @patch("tfk_mentors.email_sending.get_connection")
    def test_generic_exception_wrapped_in_connection_error(self, mock_get_connection):
        mock_get_connection.return_value.open.side_effect = RuntimeError("boom")
        with self.assertRaises(ConnectionError) as ctx:
            _verify_email_delivery()
        self.assertIn("not configured correctly", str(ctx.exception))
        self.assertIn("boom", str(ctx.exception))


class SendReplyRemindersEdgeCaseTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2026)

    def test_raises_for_email_not_yet_sent(self):
        email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() + timedelta(days=1),
            body_text="Hi",
            recipient_season=self.season,
        )
        with self.assertRaises(ValueError):
            send_reply_reminders(email)

    def test_returns_zero_sent_when_all_pending_mentors_lack_usable_email(self):
        # Whitespace-only email passes the queryset's exclude(email="") filter
        # but is filtered out by send_reply_reminders' own strip() check.
        mentor = Mentor.objects.create(
            first_name="Blank",
            last_name="Email",
            email=" ",
            type=MentorTypes.REMOTE,
        )
        mentor.seasons.add(self.season)
        email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() - timedelta(days=1),
            body_text="Hi",
            recipient_season=self.season,
        )
        email.sync_mentor_tokens()
        email.task_completed_at = timezone.now()
        email.mark_sent_recipients()
        email.save(
            update_fields=[
                "task_completed_at",
                "recipients_emailed_count",
                "updated_at",
            ]
        )
        result = send_reply_reminders(email)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["recipients"], 0)
