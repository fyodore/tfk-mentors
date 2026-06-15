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


class PracticeMentorAvailableTests(TestCase):
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
        self.mentor = Mentor.objects.create(
            first_name="Pat",
            last_name="Mentor",
            email="pat@example.com",
            cell_phone="555-0100",
            type=MentorTypes.PRACTICE,
            pace="11-12",
            split_practice=False,
        )
        self.mentor.seasons.add(self.season)

        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() + timedelta(days=1),
            body_text="Hello",
            recipient_season=self.season,
        )
        scheduled.practices.add(self.practice)
        scheduled.sync_mentor_tokens()
        self.token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=scheduled,
            mentor=self.mentor,
        )
        self.reply = ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=self.token,
            mentor=self.mentor,
            practice=self.practice,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="11-12",
        )
        self.practice.sync_mentor_assignments_from_replies()

    def test_make_mentor_available_moves_them_off_roster(self):
        response = self.client.patch(
            f"/api/practice/{self.practice.id}/mentor-replies/",
            {"mentor": self.mentor.id, "attendance": "available"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["attendance"], "available")

        self.practice.refresh_from_db()
        self.assertFalse(
            MentorPracticeAssignment.objects.filter(
                practice=self.practice,
                mentor=self.mentor,
            ).exists()
        )
        self.assertNotIn(self.mentor.id, list(self.practice.mentors.values_list("pk", flat=True)))

    def test_practice_detail_lists_available_mentors_separately(self):
        self.reply.attendance = PracticeAttendanceReply.AVAILABLE
        self.reply.save(update_fields=["attendance", "updated_at"])
        self.practice.sync_mentor_assignments_from_replies()

        response = self.client.get(f"/api/practice/{self.practice.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["mentor_replies"], [])
        self.assertEqual(len(response.data["available_mentor_replies"]), 1)
        self.assertEqual(
            response.data["available_mentor_replies"][0]["mentor_id"],
            self.mentor.id,
        )

    def test_add_available_mentor_back_to_practice(self):
        self.reply.attendance = PracticeAttendanceReply.AVAILABLE
        self.reply.save(update_fields=["attendance", "updated_at"])
        self.practice.sync_mentor_assignments_from_replies()

        response = self.client.post(
            f"/api/practice/{self.practice.id}/mentor-replies/",
            {"mentor": self.mentor.id, "pace": "11-12"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["attendance"], "attending")

        self.practice.refresh_from_db()
        self.assertTrue(
            MentorPracticeAssignment.objects.filter(
                practice=self.practice,
                mentor=self.mentor,
            ).exists()
        )

    def test_roster_report_includes_available_mentors(self):
        self.reply.attendance = PracticeAttendanceReply.AVAILABLE
        self.reply.save(update_fields=["attendance", "updated_at"])
        self.practice.sync_mentor_assignments_from_replies()

        response = self.client.get("/api/reports/practice-roster/")
        self.assertEqual(response.status_code, 200)
        practice_row = response.data[0]
        self.assertEqual(len(practice_row["mentors"]), 0)
        self.assertEqual(len(practice_row["available_mentors"]), 1)
        self.assertTrue(practice_row["available_mentors"][0]["available"])
