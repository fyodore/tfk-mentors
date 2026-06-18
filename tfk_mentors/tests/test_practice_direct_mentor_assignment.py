from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import (
    Mentor,
    MentorPracticeAssignment,
    MentorTypes,
    PaceTypes,
    Practice,
    Season,
)


class PracticeDirectMentorAssignmentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

        self.season = Season.objects.create(year=2026)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=3),
            season=self.season,
            full_practice=True,
        )
        self.mentor = Mentor.objects.create(
            first_name="Pat",
            last_name="Mentor",
            email="pat@example.com",
            cell_phone="555-0100",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.TEN.value,
        )
        self.mentor.seasons.add(self.season)

    def test_add_mentor_without_scheduled_email(self):
        url = f"/api/practice/{self.practice.id}/mentor-replies/"
        response = self.client.post(
            url,
            {"mentor": self.mentor.id, "pace": PaceTypes.TEN.value},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.data["scheduled_email_id"])
        self.assertTrue(
            MentorPracticeAssignment.objects.filter(
                mentor=self.mentor,
                practice=self.practice,
                pace=PaceTypes.TEN.value,
            ).exists()
        )

        detail = self.client.get(f"/api/practice/{self.practice.id}/")
        self.assertEqual(detail.status_code, 200)
        mentor_ids = [row["mentor_id"] for row in detail.data["mentor_replies"]]
        self.assertIn(self.mentor.id, mentor_ids)

    def test_remove_direct_assignment_without_scheduled_email(self):
        self.client.post(
            f"/api/practice/{self.practice.id}/mentor-replies/",
            {"mentor": self.mentor.id, "pace": PaceTypes.TEN.value},
            format="json",
        )

        response = self.client.delete(
            f"/api/practice/{self.practice.id}/mentor-replies/?mentor={self.mentor.id}"
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            MentorPracticeAssignment.objects.filter(
                mentor=self.mentor,
                practice=self.practice,
            ).exists()
        )

    def test_make_direct_assignment_available_without_scheduled_email(self):
        self.client.post(
            f"/api/practice/{self.practice.id}/mentor-replies/",
            {"mentor": self.mentor.id, "pace": PaceTypes.TEN.value},
            format="json",
        )

        response = self.client.patch(
            f"/api/practice/{self.practice.id}/mentor-replies/",
            {"mentor": self.mentor.id, "attendance": "available"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["attendance"], "available")

        assignment = MentorPracticeAssignment.objects.get(
            mentor=self.mentor,
            practice=self.practice,
        )
        self.assertTrue(assignment.is_available)
        self.assertNotIn(
            self.mentor.id,
            list(self.practice.mentors.values_list("pk", flat=True)),
        )

        detail = self.client.get(f"/api/practice/{self.practice.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["mentor_replies"], [])
        self.assertEqual(len(detail.data["available_mentor_replies"]), 1)

    def test_update_direct_assignment_pace_without_changing_mentor_default(self):
        self.client.post(
            f"/api/practice/{self.practice.id}/mentor-replies/",
            {"mentor": self.mentor.id, "pace": PaceTypes.TEN.value},
            format="json",
        )

        response = self.client.patch(
            f"/api/practice/{self.practice.id}/mentor-replies/",
            {"mentor": self.mentor.id, "pace": PaceTypes.ELEVEN.value},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["pace"], PaceTypes.ELEVEN.value)

        assignment = MentorPracticeAssignment.objects.get(
            mentor=self.mentor,
            practice=self.practice,
        )
        self.assertEqual(assignment.pace, PaceTypes.ELEVEN.value)

        self.mentor.refresh_from_db()
        self.assertEqual(self.mentor.pace, PaceTypes.TEN.value)
