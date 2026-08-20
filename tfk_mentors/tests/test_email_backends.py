"""Tests for tfk_mentors.email_backends (Gmail REST API + Gmail OAuth2 SMTP)."""

import base64
import smtplib
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from django.core.mail import EmailMessage
from django.test import TestCase, override_settings

from tfk_mentors.email_backends import (
    GMAIL_SEND_URL,
    GmailApiEmailBackend,
    GmailOAuth2EmailBackend,
    get_gmail_access_token,
    gmail_oauth_configured,
    send_gmail_api_message,
    verify_gmail_api_access,
    xoauth2_string,
)

GMAIL_SETTINGS = {
    "GMAIL_CLIENT_ID": "client-id",
    "GMAIL_CLIENT_SECRET": "client-secret",
    "GMAIL_REFRESH_TOKEN": "refresh-token",
}

NOT_CONFIGURED = {
    "GMAIL_CLIENT_ID": "",
    "GMAIL_CLIENT_SECRET": "",
    "GMAIL_REFRESH_TOKEN": "",
}


class GmailOauthConfiguredTests(TestCase):
    @override_settings(**NOT_CONFIGURED)
    def test_false_when_nothing_set(self):
        self.assertFalse(gmail_oauth_configured())

    @override_settings(**GMAIL_SETTINGS)
    def test_true_when_all_present(self):
        self.assertTrue(gmail_oauth_configured())

    @override_settings(
        GMAIL_CLIENT_ID="client-id", GMAIL_CLIENT_SECRET="", GMAIL_REFRESH_TOKEN="refresh"
    )
    def test_false_when_partially_set(self):
        self.assertFalse(gmail_oauth_configured())


class GetGmailAccessTokenTests(TestCase):
    @override_settings(**NOT_CONFIGURED)
    def test_raises_when_not_configured(self):
        with self.assertRaises(ValueError):
            get_gmail_access_token()

    @override_settings(**GMAIL_SETTINGS)
    @patch("tfk_mentors.email_backends.Request")
    @patch("tfk_mentors.email_backends.Credentials")
    def test_returns_token_on_success(self, mock_credentials_cls, mock_request_cls):
        creds = MagicMock()
        creds.token = "access-token-123"
        mock_credentials_cls.return_value = creds

        token = get_gmail_access_token()

        self.assertEqual(token, "access-token-123")
        mock_credentials_cls.assert_called_once_with(
            token=None,
            refresh_token="refresh-token",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="client-id",
            client_secret="client-secret",
        )
        creds.refresh.assert_called_once_with(mock_request_cls.return_value)

    @override_settings(**GMAIL_SETTINGS)
    @patch("tfk_mentors.email_backends.Request")
    @patch("tfk_mentors.email_backends.Credentials")
    def test_raises_when_no_token_returned(self, mock_credentials_cls, mock_request_cls):
        creds = MagicMock()
        creds.token = None
        mock_credentials_cls.return_value = creds

        with self.assertRaises(ValueError):
            get_gmail_access_token()


class VerifyGmailApiAccessTests(TestCase):
    @patch("tfk_mentors.email_backends.get_gmail_access_token")
    def test_calls_get_access_token(self, mock_get_token):
        verify_gmail_api_access()
        mock_get_token.assert_called_once_with()

    @patch(
        "tfk_mentors.email_backends.get_gmail_access_token",
        side_effect=ValueError("not configured"),
    )
    def test_propagates_errors(self, mock_get_token):
        with self.assertRaises(ValueError):
            verify_gmail_api_access()


class SendGmailApiMessageTests(TestCase):
    @patch("tfk_mentors.email_backends.urlopen")
    def test_success_posts_encoded_message(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        send_gmail_api_message(
            access_token="tok",
            from_email="from@example.com",
            to_addrs=["to@example.com", "other@example.com"],
            subject="Subj",
            body="Body text",
        )

        mock_urlopen.assert_called_once()
        request = mock_urlopen.call_args[0][0]
        self.assertEqual(request.full_url, GMAIL_SEND_URL)
        self.assertEqual(request.get_header("Authorization"), "Bearer tok")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(request.get_method(), "POST")

    @patch("tfk_mentors.email_backends.urlopen")
    def test_http_error_raises_runtime_error_with_detail(self, mock_urlopen):
        http_error = HTTPError(
            url=GMAIL_SEND_URL,
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=BytesIO(b"invalid grant"),
        )
        mock_urlopen.side_effect = http_error

        with self.assertRaises(RuntimeError) as ctx:
            send_gmail_api_message(
                access_token="tok",
                from_email="from@example.com",
                to_addrs=["to@example.com"],
                subject="Subj",
                body="Body",
            )

        self.assertIn("400", str(ctx.exception))
        self.assertIn("invalid grant", str(ctx.exception))


class GmailApiEmailBackendTests(TestCase):
    def _message(self, to="mentor@example.com", from_email=""):
        return EmailMessage(
            subject="Hello",
            body="Body text",
            from_email=from_email,
            to=[to],
        )

    def test_no_messages_returns_zero(self):
        backend = GmailApiEmailBackend()
        self.assertEqual(backend.send_messages([]), 0)
        self.assertEqual(backend.send_messages(None), 0)

    @override_settings(EMAIL_HOST_USER="", DEFAULT_FROM_EMAIL="")
    def test_raises_when_no_from_email_configured(self):
        backend = GmailApiEmailBackend()
        with self.assertRaises(ValueError):
            backend.send_messages([self._message()])

    @override_settings(EMAIL_HOST_USER="sender@example.com")
    @patch("tfk_mentors.email_backends.send_gmail_api_message")
    @patch("tfk_mentors.email_backends.get_gmail_access_token", return_value="tok")
    def test_sends_all_messages_successfully(self, mock_get_token, mock_send):
        backend = GmailApiEmailBackend()
        messages = [
            self._message(to="a@example.com"),
            self._message(to="b@example.com"),
        ]

        sent = backend.send_messages(messages)

        self.assertEqual(sent, 2)
        mock_get_token.assert_called_once_with()
        self.assertEqual(mock_send.call_count, 2)

    @override_settings(EMAIL_HOST_USER="sender@example.com")
    @patch("tfk_mentors.email_backends.send_gmail_api_message")
    @patch("tfk_mentors.email_backends.get_gmail_access_token", return_value="tok")
    def test_uses_message_from_email_when_set(self, mock_get_token, mock_send):
        backend = GmailApiEmailBackend()
        message = self._message(from_email="custom@example.com")

        backend.send_messages([message])

        _, kwargs = mock_send.call_args
        self.assertEqual(kwargs["from_email"], "custom@example.com")
        self.assertEqual(kwargs["access_token"], "tok")
        self.assertEqual(kwargs["to_addrs"], ["mentor@example.com"])

    @override_settings(EMAIL_HOST_USER="sender@example.com")
    @patch("tfk_mentors.email_backends.send_gmail_api_message")
    @patch("tfk_mentors.email_backends.get_gmail_access_token", return_value="tok")
    def test_falls_back_to_from_email_setting(self, mock_get_token, mock_send):
        backend = GmailApiEmailBackend()
        message = self._message(from_email="")
        # EmailMessage.__init__ backfills an empty from_email with
        # settings.DEFAULT_FROM_EMAIL, so force it blank to exercise the
        # backend's own fallback to `from_email` (EMAIL_HOST_USER).
        message.from_email = ""

        backend.send_messages([message])

        _, kwargs = mock_send.call_args
        self.assertEqual(kwargs["from_email"], "sender@example.com")

    @override_settings(EMAIL_HOST_USER="sender@example.com")
    @patch(
        "tfk_mentors.email_backends.send_gmail_api_message",
        side_effect=RuntimeError("boom"),
    )
    @patch("tfk_mentors.email_backends.get_gmail_access_token", return_value="tok")
    def test_raises_when_not_fail_silently(self, mock_get_token, mock_send):
        backend = GmailApiEmailBackend()
        with self.assertRaises(RuntimeError):
            backend.send_messages([self._message()])

    @override_settings(EMAIL_HOST_USER="sender@example.com")
    @patch(
        "tfk_mentors.email_backends.send_gmail_api_message",
        side_effect=RuntimeError("boom"),
    )
    @patch("tfk_mentors.email_backends.get_gmail_access_token", return_value="tok")
    def test_fail_silently_swallows_errors_and_counts_remaining(
        self, mock_get_token, mock_send
    ):
        backend = GmailApiEmailBackend(fail_silently=True)
        messages = [self._message(to="a@example.com"), self._message(to="b@example.com")]

        sent = backend.send_messages(messages)

        self.assertEqual(sent, 0)
        self.assertEqual(mock_send.call_count, 2)

    @override_settings(EMAIL_HOST_USER="sender@example.com")
    @patch(
        "tfk_mentors.email_backends.get_gmail_access_token",
        side_effect=ValueError("no refresh token"),
    )
    def test_raises_when_access_token_unavailable(self, mock_get_token):
        backend = GmailApiEmailBackend()
        with self.assertRaises(ValueError):
            backend.send_messages([self._message()])


class Xoauth2StringTests(TestCase):
    def test_encodes_expected_sasl_string(self):
        encoded = xoauth2_string("user@example.com", "tok123")
        decoded = base64.b64decode(encoded).decode()
        self.assertEqual(decoded, "user=user@example.com\1auth=Bearer tok123\1\1")


@override_settings(EMAIL_HOST_USER="sender@example.com")
class GmailOAuth2EmailBackendTests(TestCase):
    def test_open_returns_false_when_connection_already_open(self):
        backend = GmailOAuth2EmailBackend()
        backend.connection = MagicMock()
        self.assertFalse(backend.open())

    @override_settings(**NOT_CONFIGURED)
    def test_open_raises_when_oauth_not_configured(self):
        backend = GmailOAuth2EmailBackend()
        with self.assertRaises(ValueError):
            backend.open()

    @override_settings(**GMAIL_SETTINGS)
    @patch("tfk_mentors.email_backends.get_gmail_access_token", return_value="tok")
    @patch("smtplib.SMTP")
    def test_open_success_authenticates_with_xoauth2_and_starttls(
        self, mock_smtp_cls, mock_get_token
    ):
        mock_connection = MagicMock()
        mock_connection.docmd.return_value = (235, b"Authentication successful")
        mock_smtp_cls.return_value = mock_connection

        backend = GmailOAuth2EmailBackend(use_tls=True, use_ssl=False)

        result = backend.open()

        self.assertTrue(result)
        mock_connection.starttls.assert_called_once()
        mock_get_token.assert_called_once_with()
        auth_call = mock_connection.docmd.call_args[0]
        self.assertEqual(auth_call[0], "AUTH")
        self.assertTrue(auth_call[1].startswith("XOAUTH2 "))
        expected_auth = xoauth2_string("sender@example.com", "tok")
        self.assertEqual(auth_call[1], f"XOAUTH2 {expected_auth}")

    @override_settings(**GMAIL_SETTINGS)
    @patch("tfk_mentors.email_backends.get_gmail_access_token", return_value="tok")
    @patch("smtplib.SMTP_SSL")
    def test_open_success_over_ssl_skips_starttls(self, mock_smtp_ssl_cls, mock_get_token):
        mock_connection = MagicMock()
        mock_connection.docmd.return_value = (235, b"OK")
        mock_smtp_ssl_cls.return_value = mock_connection

        backend = GmailOAuth2EmailBackend(use_tls=False, use_ssl=True)

        result = backend.open()

        self.assertTrue(result)
        mock_connection.starttls.assert_not_called()

    @override_settings(**GMAIL_SETTINGS)
    @patch("tfk_mentors.email_backends.get_gmail_access_token", return_value="tok")
    @patch("smtplib.SMTP")
    def test_open_raises_smtp_auth_error_on_bad_code(self, mock_smtp_cls, mock_get_token):
        mock_connection = MagicMock()
        mock_connection.docmd.return_value = (535, b"Authentication failed")
        mock_smtp_cls.return_value = mock_connection

        backend = GmailOAuth2EmailBackend(use_tls=True, use_ssl=False)

        with self.assertRaises(smtplib.SMTPAuthenticationError):
            backend.open()

    @override_settings(**GMAIL_SETTINGS)
    @patch("tfk_mentors.email_backends.get_gmail_access_token", return_value="tok")
    @patch("smtplib.SMTP")
    def test_open_auth_error_response_as_string_is_encoded(
        self, mock_smtp_cls, mock_get_token
    ):
        mock_connection = MagicMock()
        mock_connection.docmd.return_value = (535, "not-bytes-response")
        mock_smtp_cls.return_value = mock_connection

        backend = GmailOAuth2EmailBackend(use_tls=True, use_ssl=False)

        with self.assertRaises(smtplib.SMTPAuthenticationError) as ctx:
            backend.open()
        self.assertEqual(ctx.exception.smtp_error, b"not-bytes-response")

    @override_settings(GMAIL_CLIENT_ID="id", GMAIL_CLIENT_SECRET="secret",
                        GMAIL_REFRESH_TOKEN="refresh", EMAIL_HOST_USER="")
    @patch("smtplib.SMTP")
    def test_open_raises_when_no_email_host_user_configured(self, mock_smtp_cls):
        mock_smtp_cls.return_value = MagicMock()
        backend = GmailOAuth2EmailBackend(username=None, use_tls=True, use_ssl=False)

        with self.assertRaises(ValueError):
            backend.open()

    @override_settings(**GMAIL_SETTINGS)
    @patch("smtplib.SMTP", side_effect=OSError("connection refused"))
    def test_open_reraises_oserror_when_not_fail_silently(self, mock_smtp_cls):
        backend = GmailOAuth2EmailBackend(use_tls=True, use_ssl=False, fail_silently=False)
        with self.assertRaises(OSError):
            backend.open()

    @override_settings(**GMAIL_SETTINGS)
    @patch("smtplib.SMTP", side_effect=OSError("connection refused"))
    def test_open_swallows_oserror_when_fail_silently(self, mock_smtp_cls):
        backend = GmailOAuth2EmailBackend(use_tls=True, use_ssl=False, fail_silently=True)
        result = backend.open()
        self.assertIsNone(result)
