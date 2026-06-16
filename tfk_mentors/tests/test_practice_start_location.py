from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import Practice, Season


class PracticeStartLocationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()
        self.season = Season.objects.create(year=2026)

    def test_create_practice_with_start_location(self):
        response = self.client.post(
            "/api/practice/",
            {
                "date": (timezone.now() + timedelta(days=3)).isoformat(),
                "season": self.season.id,
                "full_practice": True,
                "start_location": "Central Park, East 90th Street",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["start_location"], "Central Park, East 90th Street"
        )
        practice = Practice.objects.get(pk=response.data["id"])
        self.assertEqual(
            practice.get_start_location(), "Central Park, East 90th Street"
        )
