"""Gmail SMTP backend using OAuth2 refresh token (AUTH XOAUTH2)."""

import base64
import smtplib

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend
from django.core.mail.utils import DNS_NAME
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


def gmail_oauth_configured():
    return bool(
        getattr(settings, "GMAIL_CLIENT_ID", "")
        and getattr(settings, "GMAIL_CLIENT_SECRET", "")
        and getattr(settings, "GMAIL_REFRESH_TOKEN", "")
    )


def get_gmail_access_token():
    creds = Credentials(
        token=None,
        refresh_token=settings.GMAIL_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GMAIL_CLIENT_ID,
        client_secret=settings.GMAIL_CLIENT_SECRET,
    )
    creds.refresh(Request())
    if not creds.token:
        raise ValueError("Google OAuth did not return an access token.")
    return creds.token


def xoauth2_string(email, access_token):
    raw = f"user={email}\1auth=Bearer {access_token}\1\1"
    return base64.b64encode(raw.encode()).decode()


class GmailOAuth2EmailBackend(EmailBackend):
    """Send mail through Gmail SMTP using a stored OAuth refresh token."""

    def open(self):
        if self.connection:
            return False

        if not gmail_oauth_configured():
            raise ValueError(
                "Gmail OAuth2 backend requires GMAIL_CLIENT_ID, "
                "GMAIL_CLIENT_SECRET, and GMAIL_REFRESH_TOKEN."
            )

        connection_params = {"local_hostname": DNS_NAME.get_fqdn()}
        if self.timeout is not None:
            connection_params["timeout"] = self.timeout
        if self.use_ssl:
            connection_params["context"] = self.ssl_context

        try:
            self.connection = self.connection_class(
                self.host, self.port, **connection_params
            )

            if not self.use_ssl and self.use_tls:
                self.connection.starttls(context=self.ssl_context)

            user = self.username or settings.EMAIL_HOST_USER
            if not user:
                raise ValueError(
                    "EMAIL_HOST_USER must be set to the Gmail address that owns "
                    "the OAuth refresh token."
                )

            access_token = get_gmail_access_token()
            auth_string = xoauth2_string(user, access_token)
            code, response = self.connection.docmd("AUTH", "XOAUTH2 " + auth_string)
            if code != 235:
                raise smtplib.SMTPAuthenticationError(
                    code, response if isinstance(response, bytes) else str(response).encode()
                )
            return True
        except OSError:
            if not self.fail_silently:
                raise
