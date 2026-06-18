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


class AddAvailableMentorMultiEmailTests(TestCase):
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
        )
        self.mentor.seasons.add(self.season)

        self.first_email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() - timedelta(days=7),
            body_text="First",
            recipient_season=self.season,
            task_completed_at=timezone.now() - timedelta(days=7),
        )
        self.first_email.practices.add(self.practice)
        self.first_token = ScheduledEmailMentorToken.objects.create(
            scheduled_email=self.first_email,
            mentor=self.mentor,
            included_in_send=True,
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=self.first_token,
            mentor=self.mentor,
            practice=self.practice,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="11-12",
        )
        self.practice.sync_mentor_assignments_from_replies()

        self.second_email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() - timedelta(days=1),
            body_text="Second",
            recipient_season=self.season,
            task_completed_at=timezone.now() - timedelta(days=1),
        )
        self.second_email.practices.add(self.practice)
        self.second_email.sync_mentor_tokens()

    def test_add_available_mentor_back_when_newer_scheduled_email_exists(self):
        self.client.patch(
            f"/api/practice/{self.practice.id}/mentor-replies/",
            {"mentor": self.mentor.id, "attendance": "available"},
            format="json",
        )

        response = self.client.post(
            f"/api/practice/{self.practice.id}/mentor-replies/",
            {"mentor": self.mentor.id, "pace": "11-12"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["attendance"], "attending")
