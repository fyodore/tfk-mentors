from django.test import TestCase
from rest_framework.test import APIClient

from tfk_mentors.models import Coach, Season


class SeasonHeadCoachTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

        self.season = Season.objects.create(year=2026)
        self.coach = Coach.objects.create(
            first_name="Harper",
            last_name="Head",
            email="harper@example.com",
        )
        self.coach.seasons.add(self.season)
        self.other_coach = Coach.objects.create(
            first_name="Other",
            last_name="Coach",
            email="other@example.com",
        )

    def test_set_head_coach_for_season(self):
        response = self.client.patch(
            f"/api/season/{self.season.id}/",
            {"head_coach": self.coach.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["head_coach"], self.coach.id)

    def test_head_coach_must_belong_to_season(self):
        response = self.client.patch(
            f"/api/season/{self.season.id}/",
            {"head_coach": self.other_coach.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
