from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import Practice, Season


class PracticeListSeasonFilterTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()
        self.season_a = Season.objects.create(year=2025)
        self.season_b = Season.objects.create(year=2026, is_current=True)
        self.practice_a = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=self.season_a,
            description="A season practice",
            attendance_comments="secret notes",
        )
        self.practice_b = Practice.objects.create(
            date=timezone.now() + timedelta(days=2),
            season=self.season_b,
            description="B season practice",
            attendance_comments="more notes",
        )

    def test_list_all_practices_without_season_param(self):
        response = self.client.get("/api/practice/")
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.data}
        self.assertEqual(ids, {self.practice_a.id, self.practice_b.id})

    def test_list_filters_by_season(self):
        response = self.client.get(f"/api/practice/?season={self.season_b.id}")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data]
        self.assertEqual(ids, [self.practice_b.id])

    def test_list_omits_heavy_fields(self):
        response = self.client.get(f"/api/practice/?season={self.season_b.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        row = response.data[0]
        self.assertNotIn("mentors", row)
        self.assertNotIn("attendance_comments", row)
        self.assertEqual(row["description"], "B season practice")

    def test_list_invalid_season_returns_empty(self):
        response = self.client.get("/api/practice/?season=not-a-number")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])
