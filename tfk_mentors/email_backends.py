"""Gmail email backends: REST API (default) or SMTP+OAuth2."""

import base64
import json
import smtplib
import time
from email.message import EmailMessage
from urllib.error import HTTPError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend
from django.core.mail.utils import DNS_NAME
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# messages.send costs 100 quota units; default user cap is 6000 units/min (~60/min).
_DEFAULT_SEND_MIN_INTERVAL_SECONDS = 1.1
_DEFAULT_SEND_MAX_RETRIES = 6


def _gmail_send_min_interval_seconds():
    raw = getattr(settings, "GMAIL_SEND_MIN_INTERVAL_SECONDS", None)
    if raw is None or raw == "":
        return _DEFAULT_SEND_MIN_INTERVAL_SECONDS
    return max(0.0, float(raw))


def _gmail_send_max_retries():
    raw = getattr(settings, "GMAIL_SEND_MAX_RETRIES", None)
    if raw is None or raw == "":
        return _DEFAULT_SEND_MAX_RETRIES
    return max(0, int(raw))


def _is_gmail_rate_limit_error(status_code: int, detail: str) -> bool:
    if status_code not in (403, 429):
        return False
    lowered = (detail or "").lower()
    return any(
        token in lowered
        for token in (
            "ratelimitexceeded",
            "rate_limit_exceeded",
            "quota exceeded",
            "usagelimitsexceeded",
        )
    )


def gmail_oauth_configured():
    return bool(
        getattr(settings, "GMAIL_CLIENT_ID", "")
        and getattr(settings, "GMAIL_CLIENT_SECRET", "")
        and getattr(settings, "GMAIL_REFRESH_TOKEN", "")
    )


def get_gmail_access_token():
    if not gmail_oauth_configured():
        raise ValueError(
            "Gmail OAuth requires GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, "
            "and GMAIL_REFRESH_TOKEN."
        )
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


def verify_gmail_api_access():
    """Refresh OAuth token to confirm Gmail API credentials work."""
    get_gmail_access_token()


def send_gmail_api_message(*, access_token, from_email, to_addrs, subject, body):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = ", ".join(to_addrs)
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload = json.dumps({"raw": raw}).encode()
    timeout = getattr(settings, "EMAIL_TIMEOUT", 30)
    max_retries = _gmail_send_max_retries()

    for attempt in range(max_retries + 1):
        req = UrlRequest(
            GMAIL_SEND_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=timeout) as resp:
                resp.read()
            return
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            if attempt < max_retries and _is_gmail_rate_limit_error(exc.code, detail):
                # ~60s window for per-minute quota; backoff up to that.
                time.sleep(min(60.0, float(2 ** attempt)))
                continue
            raise RuntimeError(
                f"Gmail API send failed ({exc.code}): {detail}"
            ) from exc


class GmailApiEmailBackend(BaseEmailBackend):
    """Send mail via Gmail REST API (HTTPS) using an OAuth refresh token."""

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        from_email = settings.EMAIL_HOST_USER or settings.DEFAULT_FROM_EMAIL
        if not from_email:
            raise ValueError(
                "EMAIL_HOST_USER must be set to the Gmail address that owns "
                "the OAuth refresh token."
            )

        access_token = get_gmail_access_token()
        interval = _gmail_send_min_interval_seconds()
        last_send_at = None
        sent = 0
        for message in email_messages:
            if last_send_at is not None and interval > 0:
                wait_for = interval - (time.monotonic() - last_send_at)
                if wait_for > 0:
                    time.sleep(wait_for)
            try:
                send_gmail_api_message(
                    access_token=access_token,
                    from_email=message.from_email or from_email,
                    to_addrs=message.to,
                    subject=message.subject,
                    body=message.body,
                )
            except Exception:
                if not self.fail_silently:
                    raise
            else:
                sent += 1
            finally:
                last_send_at = time.monotonic()
        return sent


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
                    code,
                    response if isinstance(response, bytes) else str(response).encode(),
                )
            return True
        except OSError:
            if not self.fail_silently:
                raise
