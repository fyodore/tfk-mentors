from django.conf import settings
from django.core.mail import get_connection, send_mail
from django.core.management.base import BaseCommand, CommandError

from tfk_mentors.email_backends import gmail_oauth_configured


class Command(BaseCommand):
    help = "Test SMTP settings by opening a connection and optionally sending one email."

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            help="Send a test message to this address after the connection check.",
        )

    def handle(self, *args, **options):
        self.stdout.write(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"EMAIL_HOST: {settings.EMAIL_HOST}")
        self.stdout.write(f"EMAIL_PORT: {settings.EMAIL_PORT}")
        self.stdout.write(f"EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"EMAIL_USE_SSL: {settings.EMAIL_USE_SSL}")
        self.stdout.write(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER or '(empty)'}")
        self.stdout.write(
            "Auth: "
            + (
                "Gmail OAuth2 refresh token"
                if gmail_oauth_configured()
                else "SMTP username/password"
            )
        )
        self.stdout.write(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")

        try:
            connection = get_connection(fail_silently=False)
            connection.open()
            connection.close()
        except Exception as exc:
            raise CommandError(
                "SMTP connection failed.\n"
                f"Host: {settings.EMAIL_HOST}:{settings.EMAIL_PORT}\n"
                f"Backend: {settings.EMAIL_BACKEND}\n"
                f"Error: {exc}\n\n"
                "If OAuth: verify GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, "
                "GMAIL_REFRESH_TOKEN, and EMAIL_HOST_USER match the authorized Gmail.\n"
                "If blocked: try port 465 + EMAIL_USE_SSL=1, or use SendGrid/Mailgun."
            ) from exc

        self.stdout.write(self.style.SUCCESS("SMTP connection OK."))

        to_addr = options.get("to")
        if not to_addr:
            return

        send_mail(
            subject="TFK Mentors SMTP test",
            message="If you received this, SMTP is configured correctly.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_addr],
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS(f"Test email sent to {to_addr}."))
