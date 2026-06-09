from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import (
    Mentor,
    MentorTypes,
    Practice,
    PracticeAttendanceReply,
    ScheduledEmail,
    ScheduledEmailMentorPracticeReply,
    ScheduledEmailMentorToken,
    Season,
)


class PracticeRosterReportTests(TestCase):
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
            pace="8--9",
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
        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=scheduled,
            mentor=self.mentor,
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token,
            mentor=self.mentor,
            practice=self.practice,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="8--9",
        )

    def test_roster_counts_attending_mentor_with_normalized_pace(self):
        response = self.client.get("/api/reports/practice-roster/")

        self.assertEqual(response.status_code, 200)
        practice_row = response.data[0]
        self.assertEqual(len(practice_row["mentors"]), 1)
        self.assertEqual(practice_row["mentors"][0]["pace"], "8-9")
        pace_rows = {
            row["pace"]: row["count"] for row in practice_row["mentor_pace_counts"]
        }
        self.assertEqual(pace_rows["8-9"], 1)
