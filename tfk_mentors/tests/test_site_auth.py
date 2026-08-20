from django.test import TestCase
from rest_framework.test import APIClient

from tfk_mentors import settings


class SiteAuthViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_session_check_when_not_authenticated(self):
        response = self.client.get("/api/auth/session/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["authenticated"])

    def test_session_check_when_authenticated(self):
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

        response = self.client.get("/api/auth/session/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["authenticated"])

    def test_login_success(self):
        response = self.client.post(
            "/api/auth/session/",
            {"password": settings.SITE_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["detail"], "Authenticated.")
        self.assertTrue(self.client.session.get("site_authenticated"))

    def test_login_failure_wrong_password(self):
        response = self.client.post(
            "/api/auth/session/",
            {"password": "wrong-password"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["detail"], "Invalid password.")
        self.assertIsNone(self.client.session.get("site_authenticated"))

    def test_login_failure_missing_password(self):
        response = self.client.post("/api/auth/session/", {}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_logout_clears_session(self):
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

        response = self.client.delete("/api/auth/session/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["detail"], "Logged out.")

        check = self.client.get("/api/auth/session/")
        self.assertFalse(check.data["authenticated"])


class SiteConfigViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_returns_time_zone(self):
        response = self.client.get("/api/config/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["time_zone"], settings.TIME_ZONE)
