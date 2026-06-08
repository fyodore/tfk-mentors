#!/usr/bin/env python3
"""
One-time local script to obtain a Gmail API refresh token.

Usage (on your laptop, not the production server):
  pip install google-auth-oauthlib google-auth-httplib2
  python scripts/get_gmail_refresh_token.py

Then set on the server in production.py / environment:
  GMAIL_CLIENT_ID
  GMAIL_CLIENT_SECRET
  GMAIL_REFRESH_TOKEN
  EMAIL_HOST_USER=<the Gmail address you signed in with>
"""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def main():
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(
        port=8080,
        access_type="offline",
        prompt="consent",
    )
    if not creds.refresh_token:
        raise SystemExit(
            "No refresh token returned. Revoke this app at "
            "https://myaccount.google.com/permissions and run again."
        )

    print("\nAdd these to production (keep the refresh token secret):\n")
    print(f"GMAIL_CLIENT_ID={creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print("\nAlso set EMAIL_HOST_USER to the Gmail account you authorized.")


if __name__ == "__main__":
    main()
