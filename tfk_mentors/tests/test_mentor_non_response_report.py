from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import (
    Mentor,
    Practice,
    PracticeAttendanceReply,
    ScheduledEmail,
    ScheduledEmailMentorPracticeReply,
    ScheduledEmailMentorToken,
    Season,
)


class MentorNonResponseReportTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

        self.season = Season.objects.create(year=2026)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=7),
            season=self.season,
        )
        self.mentor_responded = Mentor.objects.create(
            first_name="Amy",
            last_name="Alpha",
            email="amy@example.com",
            cell_phone="5551111111",
            type="At Practice",
            pace="8-9",
        )
        self.mentor_pending = Mentor.objects.create(
            first_name="Bob",
            last_name="Beta",
            email="bob@example.com",
            cell_phone="5552222222",
            type="Remote",
            pace="9-10",
        )
        self.mentor_responded.seasons.add(self.season)
        self.mentor_pending.seasons.add(self.season)

        self.scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() - timedelta(days=1),
            task_completed_at=timezone.now() - timedelta(hours=1),
            body_text="Hi {{ first_name }}",
            recipient_season=self.season,
        )
        self.scheduled.practices.add(self.practice)
        self.scheduled.sync_mentor_tokens()

        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=self.scheduled,
            mentor=self.mentor_responded,
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token,
            mentor=self.mentor_responded,
            practice=self.practice,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="8-9",
        )

    def test_pending_mentor_listed_without_reply(self):
        response = self.client.get("/api/reports/mentor-non-responses/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["mentors_emailed"], 2)
        self.assertEqual(response.data["summary"]["mentors_responded"], 1)
        self.assertEqual(len(response.data["practices"]), 1)
        practice_row = response.data["practices"][0]
        self.assertTrue(practice_row["email_sent"])
        self.assertEqual(practice_row["mentors_emailed"], 2)
        self.assertEqual(practice_row["mentors_responded"], 1)
        self.assertEqual(len(practice_row["pending_mentors"]), 1)
        self.assertEqual(practice_row["pending_mentors"][0]["email"], "bob@example.com")
