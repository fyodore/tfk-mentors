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


class PracticeMentorSwapTests(TestCase):
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
        self.outgoing = Mentor.objects.create(
            first_name="Out",
            last_name="Going",
            email="out@example.com",
            cell_phone="555-0100",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.TEN.value,
        )
        self.incoming = Mentor.objects.create(
            first_name="In",
            last_name="Coming",
            email="in@example.com",
            cell_phone="555-0101",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.EIGHT.value,
        )
        self.outgoing.seasons.add(self.season)
        self.incoming.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=self.outgoing,
            practice=self.practice,
            pace=self.outgoing.pace,
            is_available=False,
        )
        self.practice.mentors.add(self.outgoing)

    def test_swap_replaces_mentor_and_records_found_replacement(self):
        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["outgoing_mentor_id"], self.outgoing.id)
        self.assertEqual(response.data["show_up"], ShowUpStatus.FOUND_REPLACEMENT)

        self.practice.refresh_from_db()
        self.assertNotIn(self.outgoing, self.practice.mentors.all())
        self.assertIn(self.incoming, self.practice.mentors.all())
        show_up = MentorPracticeShowUp.objects.get(
            mentor=self.outgoing,
            practice=self.practice,
        )
        self.assertEqual(show_up.show_up, ShowUpStatus.FOUND_REPLACEMENT)

    def test_attendance_payload_includes_swapped_out_mentor(self):
        self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        response = self.client.get(f"/api/practice-attendance/{self.practice.id}/")
        self.assertEqual(response.status_code, 200)
        mentors = response.data["assigned_mentors"]
        swapped = next(
            row for row in mentors if row["mentor_id"] == self.outgoing.id
        )
        self.assertTrue(swapped["swapped_out"])
        self.assertEqual(swapped["show_up"], ShowUpStatus.FOUND_REPLACEMENT)

    def test_archived_attendance_counts_found_replacement(self):
        self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.practice.date = timezone.now() - timedelta(days=2)
        self.practice.save(update_fields=["date", "updated_at"])

        response = self.client.get("/api/practice-attendance/archived/")
        self.assertEqual(response.status_code, 200)
        row = next(
            item for item in response.data if item["practice_id"] == self.practice.id
        )
        self.assertEqual(row["found_replacement_count"], 1)
        self.assertEqual(row["assigned_count"], 1)

    def test_swap_rejects_incoming_mentor_already_on_practice(self):
        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.outgoing.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
