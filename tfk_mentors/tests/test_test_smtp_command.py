"""Light coverage for the test_smtp management command (mocked, no real network)."""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

COMMAND = "test_smtp"
MODULE = "tfk_mentors.management.commands.test_smtp"


class TestSmtpCommandTests(TestCase):
    def _run(self, *args, **kwargs):
        out = StringIO()
        call_command(COMMAND, *args, stdout=out, **kwargs)
        return out.getvalue()

    @override_settings(
        EMAIL_BACKEND="tfk_mentors.email_backends.GmailApiEmailBackend",
        EMAIL_HOST_USER="sender@example.com",
    )
    @patch(f"{MODULE}.verify_gmail_api_access")
    @patch(f"{MODULE}.gmail_oauth_configured", return_value=True)
    def test_gmail_api_backend_reports_success(self, mock_configured, mock_verify):
        output = self._run()

        mock_verify.assert_called_once_with()
        self.assertIn("Gmail API OAuth token OK.", output)
        self.assertIn("Gmail REST API (HTTPS)", output)

    @override_settings(
        EMAIL_BACKEND="tfk_mentors.email_backends.GmailOAuth2EmailBackend",
        EMAIL_HOST_USER="sender@example.com",
    )
    @patch(f"{MODULE}.gmail_oauth_configured", return_value=True)
    def test_gmail_smtp_oauth_backend_uses_smtp_xoauth2_label(self, mock_configured):
        with patch("django.core.mail.get_connection") as mock_get_connection:
            mock_connection = mock_get_connection.return_value
            output = self._run()

        self.assertIn("SMTP XOAUTH2", output)
        self.assertIn("SMTP connection OK.", output)
        mock_connection.open.assert_called_once_with()
        mock_connection.close.assert_called_once_with()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST_PASSWORD="app-password",
    )
    @patch(f"{MODULE}.gmail_oauth_configured", return_value=False)
    def test_smtp_backend_reports_success(self, mock_configured):
        with patch("django.core.mail.get_connection") as mock_get_connection:
            mock_connection = mock_get_connection.return_value
            output = self._run()

        self.assertIn("SMTP connection OK.", output)
        mock_connection.open.assert_called_once_with()
        mock_connection.close.assert_called_once_with()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST_PASSWORD="",
    )
    @patch(f"{MODULE}.gmail_oauth_configured", return_value=False)
    def test_raises_when_no_auth_configured(self, mock_configured):
        with self.assertRaises(CommandError) as ctx:
            self._run()
        self.assertIn("No email auth configured", str(ctx.exception))

    @override_settings(
        EMAIL_BACKEND="tfk_mentors.email_backends.GmailApiEmailBackend",
        EMAIL_HOST_USER="sender@example.com",
    )
    @patch(f"{MODULE}.verify_gmail_api_access", side_effect=ValueError("bad token"))
    @patch(f"{MODULE}.gmail_oauth_configured", return_value=True)
    def test_connection_failure_wrapped_in_command_error(self, mock_configured, mock_verify):
        with self.assertRaises(CommandError) as ctx:
            self._run()
        self.assertIn("Email connection failed.", str(ctx.exception))
        self.assertIn("bad token", str(ctx.exception))

    @override_settings(
        EMAIL_BACKEND="tfk_mentors.email_backends.GmailApiEmailBackend",
        EMAIL_HOST_USER="sender@example.com",
    )
    @patch(f"{MODULE}.send_mail")
    @patch(f"{MODULE}.verify_gmail_api_access")
    @patch(f"{MODULE}.gmail_oauth_configured", return_value=True)
    def test_sends_test_email_when_to_provided(
        self, mock_configured, mock_verify, mock_send_mail
    ):
        output = self._run("--to", "someone@example.com")

        mock_send_mail.assert_called_once()
        self.assertEqual(
            mock_send_mail.call_args.kwargs["recipient_list"], ["someone@example.com"]
        )
        self.assertIn("Test email sent to someone@example.com.", output)
