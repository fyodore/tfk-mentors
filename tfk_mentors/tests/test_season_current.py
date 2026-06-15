from django.test import TestCase
from rest_framework.test import APIClient

from tfk_mentors.models import Season


class SeasonCurrentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()
        self.season_2025 = Season.objects.create(year=2025, is_current=True)
        self.season_2026 = Season.objects.create(year=2026, is_current=False)

    def test_only_one_current_season_at_a_time(self):
        response = self.client.patch(
            f"/api/season/{self.season_2026.id}/",
            {"is_current": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_current"])

        self.season_2025.refresh_from_db()
        self.season_2026.refresh_from_db()
        self.assertFalse(self.season_2025.is_current)
        self.assertTrue(self.season_2026.is_current)

    def test_season_list_includes_is_current(self):
        response = self.client.get("/api/season/")
        self.assertEqual(response.status_code, 200)
        rows_by_id = {row["id"]: row for row in response.data}
        self.assertTrue(rows_by_id[self.season_2025.id]["is_current"])
        self.assertFalse(rows_by_id[self.season_2026.id]["is_current"])
