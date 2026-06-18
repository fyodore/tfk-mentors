from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import (
    Mentor,
    MentorPracticeAssignment,
    MentorPracticeShowUp,
    MentorTypes,
    PaceTypes,
    Practice,
    Season,
    ShowUpStatus,
)


class PracticeAttendanceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

        self.season = Season.objects.create(year=2026)
        self.now = timezone.now()
        self.recent_practice = Practice.objects.create(
            date=self.now - timedelta(hours=2),
            season=self.season,
            full_practice=True,
        )
        self.future_practice = Practice.objects.create(
            date=self.now + timedelta(days=5),
            season=self.season,
            full_practice=True,
        )
        self.old_practice = Practice.objects.create(
            date=self.now - timedelta(days=3),
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
        self.available_mentor = Mentor.objects.create(
            first_name="Ava",
            last_name="Available",
            email="ava@example.com",
            cell_phone="555-0101",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.EIGHT.value,
        )
        self.available_mentor.seasons.add(self.season)

    def assign_mentor(self, practice, mentor):
        MentorPracticeAssignment.objects.create(
            mentor=mentor,
            practice=practice,
            pace=mentor.pace,
            is_available=False,
        )
        practice.mentors.add(mentor)

    def test_current_practice_prefers_recent_within_window(self):
        response = self.client.get("/api/practice-attendance/current/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["practice"]["practice_id"],
            self.recent_practice.id,
        )

    def test_archived_lists_past_practices_with_show_up(self):
        self.assign_mentor(self.old_practice, self.mentor)
        MentorPracticeShowUp.objects.create(
            mentor=self.mentor,
            practice=self.old_practice,
            show_up=ShowUpStatus.ATTENDED,
        )

        response = self.client.get("/api/practice-attendance/archived/")
        self.assertEqual(response.status_code, 200)
        row = next(
            item
            for item in response.data
            if item["practice_id"] == self.old_practice.id
        )
        self.assertEqual(row["attended_count"], 1)
        self.assertEqual(row["assigned_mentors"][0]["show_up"], ShowUpStatus.ATTENDED)

    def test_patch_records_attended_and_comments(self):
        self.assign_mentor(self.recent_practice, self.mentor)
        url = f"/api/practice-attendance/{self.recent_practice.id}/"

        response = self.client.patch(
            url,
            {
                "attendance_comments": "Great turnout.",
                "mentors": [
                    {"mentor_id": self.mentor.id, "show_up": ShowUpStatus.ATTENDED}
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["attendance_comments"], "Great turnout.")
        self.assertEqual(
            response.data["assigned_mentors"][0]["show_up"],
            ShowUpStatus.ATTENDED,
        )
        self.recent_practice.refresh_from_db()
        self.assertEqual(self.recent_practice.attendance_comments, "Great turnout.")

    def test_patch_rejects_available_only_mentor(self):
        MentorPracticeAssignment.objects.create(
            mentor=self.available_mentor,
            practice=self.recent_practice,
            pace=self.available_mentor.pace,
            is_available=True,
        )
        url = f"/api/practice-attendance/{self.recent_practice.id}/"

        response = self.client.patch(
            url,
            {
                "mentors": [
                    {
                        "mentor_id": self.available_mentor.id,
                        "show_up": ShowUpStatus.MISSED,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_patch_can_clear_show_up(self):
        self.assign_mentor(self.recent_practice, self.mentor)
        MentorPracticeShowUp.objects.create(
            mentor=self.mentor,
            practice=self.recent_practice,
            show_up=ShowUpStatus.MISSED,
        )
        url = f"/api/practice-attendance/{self.recent_practice.id}/"

        response = self.client.patch(
            url,
            {"mentors": [{"mentor_id": self.mentor.id, "show_up": None}]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["assigned_mentors"][0]["show_up"])
        self.assertFalse(
            MentorPracticeShowUp.objects.filter(
                mentor=self.mentor,
                practice=self.recent_practice,
            ).exists()
        )
