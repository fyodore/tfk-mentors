from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

from tfk_mentors.email_backends import (
    gmail_oauth_configured,
    verify_gmail_api_access,
)


class Command(BaseCommand):
    help = "Test email settings (Gmail API or SMTP) and optionally send one message."

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            help="Send a test message to this address after the connection check.",
        )

    def handle(self, *args, **options):
        using_gmail_api = settings.EMAIL_BACKEND.endswith("GmailApiEmailBackend")
        using_gmail_smtp_oauth = settings.EMAIL_BACKEND.endswith(
            "GmailOAuth2EmailBackend"
        )

        self.stdout.write(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
        if using_gmail_api or using_gmail_smtp_oauth:
            self.stdout.write(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER or '(empty)'}")
            self.stdout.write(
                "Auth: Gmail OAuth2 refresh token → "
                + ("Gmail REST API (HTTPS)" if using_gmail_api else "SMTP XOAUTH2")
            )
        else:
            self.stdout.write(f"EMAIL_HOST: {settings.EMAIL_HOST}")
            self.stdout.write(f"EMAIL_PORT: {settings.EMAIL_PORT}")
            self.stdout.write(f"EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
            self.stdout.write(f"EMAIL_USE_SSL: {settings.EMAIL_USE_SSL}")
            self.stdout.write(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER or '(empty)'}")
            self.stdout.write("Auth: SMTP username/password")
        self.stdout.write(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")

        if not gmail_oauth_configured() and not settings.EMAIL_HOST_PASSWORD:
            raise CommandError(
                "No email auth configured. Set either:\n"
                "  GMAIL_CLIENT_ID + GMAIL_CLIENT_SECRET + GMAIL_REFRESH_TOKEN\n"
                "or EMAIL_HOST_PASSWORD (Gmail app password)."
            )

        try:
            if using_gmail_api:
                verify_gmail_api_access()
                self.stdout.write(self.style.SUCCESS("Gmail API OAuth token OK."))
            else:
                from django.core.mail import get_connection

                connection = get_connection(fail_silently=False)
                connection.open()
                connection.close()
                self.stdout.write(self.style.SUCCESS("SMTP connection OK."))
        except Exception as exc:
            raise CommandError(
                "Email connection failed.\n"
                f"Backend: {settings.EMAIL_BACKEND}\n"
                f"Error: {exc}\n\n"
                "For Gmail API: ensure GMAIL_* vars are set in production.py and "
                "EMAIL_HOST_USER matches the authorized Gmail account.\n"
                "Generate token locally: python scripts/get_gmail_refresh_token.py"
            ) from exc

        to_addr = options.get("to")
        if not to_addr:
            return

        send_mail(
            subject="TFK Mentors email test",
            message="If you received this, email delivery is configured correctly.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_addr],
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS(f"Test email sent to {to_addr}."))
