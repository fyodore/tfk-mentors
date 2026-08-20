from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import Coach, CoachPracticeAssignment, Practice, Season


class CoachPracticeAssignmentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

        self.season = Season.objects.create(year=2026)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=7),
            season=self.season,
            full_practice=True,
        )
        self.coach = Coach.objects.create(
            first_name="Casey",
            last_name="Coach",
            email="casey@example.com",
        )
        self.coach.seasons.add(self.season)

    def test_create_coach_assignment_without_pace(self):
        response = self.client.post(
            "/api/coach-practice-assignment/",
            {
                "coach": self.coach.id,
                "practice": self.practice.id,
                "pace": "",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["pace"], "")
        assignment = CoachPracticeAssignment.objects.get(
            coach=self.coach,
            practice=self.practice,
        )
        self.assertEqual(assignment.pace, "")

    def test_coach_practices_endpoint_lists_assignments(self):
        CoachPracticeAssignment.objects.create(
            coach=self.coach,
            practice=self.practice,
            pace="8-9",
        )
        response = self.client.get(f"/api/coach/{self.coach.id}/practices/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        row = response.data[0]
        self.assertEqual(row["practice_id"], self.practice.id)
        self.assertEqual(row["pace"], "8-9")
        self.assertEqual(row["season_id"], self.season.id)
        self.assertEqual(row["season_year"], self.season.year)

    def test_coach_practices_endpoint_empty_when_unassigned(self):
        response = self.client.get(f"/api/coach/{self.coach.id}/practices/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])
