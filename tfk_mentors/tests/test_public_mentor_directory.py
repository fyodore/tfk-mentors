from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import (
    Mentor,
    MentorPracticeAssignment,
    MentorTypes,
    Practice,
    PracticeAttendanceReply,
    ScheduledEmail,
    ScheduledEmailMentorPracticeReply,
    ScheduledEmailMentorToken,
    Season,
)


class PublicMentorDirectoryTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.season = Season.objects.create(year=2026)
        self.mentor = Mentor.objects.create(
            first_name="Pat",
            last_name="Alpha",
            email="pat@example.com",
            cell_phone="555-0100",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        self.other_mentor = Mentor.objects.create(
            first_name="Sam",
            last_name="Beta",
            email="sam@example.com",
            cell_phone="555-0101",
            type=MentorTypes.PRACTICE,
            pace="10-11",
        )
        self.mentor.seasons.add(self.season)
        self.other_mentor.seasons.add(self.season)

        self.assigned_practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=7),
            season=self.season,
            nyrr_race="Long Run",
        )
        self.available_practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=14),
            season=self.season,
        )
        self.unassigned_practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=21),
            season=self.season,
        )

        self.assigned_practice.show_to_mentors = True
        self.assigned_practice.save(update_fields=["show_to_mentors", "updated_at"])
        self.available_practice.show_to_mentors = True
        self.available_practice.save(update_fields=["show_to_mentors", "updated_at"])

        MentorPracticeAssignment.objects.create(
            mentor=self.mentor,
            practice=self.assigned_practice,
            pace="9-10",
            is_available=False,
        )
        self.assigned_practice.mentors.add(self.mentor)
        MentorPracticeAssignment.objects.create(
            mentor=self.mentor,
            practice=self.available_practice,
            pace="9-10",
            is_available=True,
        )

    def test_public_endpoint_does_not_require_auth(self):
        response = self.client.get("/api/public/mentor-directory/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_public_summary_payload_excludes_contact_info_and_practices(self):
        response = self.client.get("/api/public/mentor-directory/")
        pat = next(row for row in response.data if row["last_name"] == "Alpha")

        self.assertEqual(pat["type"], MentorTypes.PRACTICE)
        self.assertEqual(pat["pace"], "9-10")
        self.assertEqual(pat["assigned_count"], 1)
        self.assertEqual(pat["available_count"], 1)
        self.assertNotIn("email", pat)
        self.assertNotIn("cell_phone", pat)
        self.assertNotIn("assigned_practices", pat)
        self.assertNotIn("available_practices", pat)

    def test_public_directory_excludes_practices_not_marked_show_to_mentors(self):
        hidden_practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=28),
            season=self.season,
            show_to_mentors=False,
        )
        MentorPracticeAssignment.objects.create(
            mentor=self.mentor,
            practice=hidden_practice,
            pace="9-10",
            is_available=False,
        )
        hidden_practice.mentors.add(self.mentor)

        summary = self.client.get("/api/public/mentor-directory/")
        pat = next(row for row in summary.data if row["last_name"] == "Alpha")
        self.assertEqual(pat["assigned_count"], 1)

        response = self.client.get(
            f"/api/public/mentor-directory/{self.mentor.id}/practices/"
        )
        practice_ids = {
            row["practice_id"]
            for row in response.data["assigned_practices"]
            + response.data["available_practices"]
        }
        self.assertIn(self.assigned_practice.id, practice_ids)
        self.assertNotIn(hidden_practice.id, practice_ids)

    def test_public_practices_endpoint_loads_on_expand(self):
        response = self.client.get(
            f"/api/public/mentor-directory/{self.mentor.id}/practices/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["assigned_practices"]), 1)
        self.assertEqual(
            response.data["assigned_practices"][0]["practice_id"],
            self.assigned_practice.id,
        )
        self.assertEqual(len(response.data["available_practices"]), 1)
        self.assertEqual(
            response.data["available_practices"][0]["practice_id"],
            self.available_practice.id,
        )
        practice_ids = {
            row["practice_id"]
            for row in response.data["assigned_practices"]
            + response.data["available_practices"]
        }
        self.assertNotIn(self.unassigned_practice.id, practice_ids)

    def test_public_practices_endpoint_includes_email_reply_assignments(self):
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() + timedelta(days=1),
            body_text="Hello",
            recipient_season=self.season,
        )
        scheduled.practices.add(self.unassigned_practice)
        scheduled.sync_mentor_tokens()
        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=scheduled,
            mentor=self.other_mentor,
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token,
            mentor=self.other_mentor,
            practice=self.unassigned_practice,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="10-11",
        )
        self.unassigned_practice.sync_mentor_assignments_from_replies()
        self.unassigned_practice.show_to_mentors = True
        self.unassigned_practice.save(update_fields=["show_to_mentors", "updated_at"])

        summary = self.client.get("/api/public/mentor-directory/")
        sam = next(row for row in summary.data if row["last_name"] == "Beta")
        self.assertEqual(sam["assigned_count"], 1)

        response = self.client.get(
            f"/api/public/mentor-directory/{self.other_mentor.id}/practices/"
        )
        self.assertEqual(len(response.data["assigned_practices"]), 1)
        self.assertEqual(
            response.data["assigned_practices"][0]["practice_id"],
            self.unassigned_practice.id,
        )

    def test_public_practice_roster_lists_attending_then_available(self):
        other_attending = Mentor.objects.create(
            first_name="Quinn",
            last_name="Coach",
            email="quinn@example.com",
            cell_phone="555-0102",
            type=MentorTypes.PRACTICE,
            pace="8-9",
        )
        other_attending.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=other_attending,
            practice=self.assigned_practice,
            pace="8-9",
            is_available=False,
        )
        self.assigned_practice.mentors.add(other_attending)

        other_available = Mentor.objects.create(
            first_name="Riley",
            last_name="Standby",
            email="riley@example.com",
            cell_phone="555-0103",
            type=MentorTypes.PRACTICE,
            pace="11-12",
        )
        other_available.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=other_available,
            practice=self.available_practice,
            pace="11-12",
            is_available=True,
        )

        response = self.client.get(
            f"/api/public/practice/{self.assigned_practice.id}/mentors/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["attending_mentors"]), 2)
        self.assertEqual(response.data["attending_mentors"][0]["last_name"], "Coach")
        self.assertNotIn("email", response.data["attending_mentors"][0])

        available_response = self.client.get(
            f"/api/public/practice/{self.available_practice.id}/mentors/"
        )
        self.assertEqual(len(available_response.data["available_mentors"]), 2)
