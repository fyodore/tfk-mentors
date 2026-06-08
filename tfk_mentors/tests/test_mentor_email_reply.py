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


class MentorEmailReplySubmitTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()
        self.season = Season.objects.create(year=2026)
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
        now = timezone.now()
        self.practices = [
            Practice.objects.create(
                date=now + timedelta(days=offset),
                season=self.season,
                full_practice=True,
            )
            for offset in (1, 2, 3, 4)
        ]
        self.scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=now + timedelta(days=7),
            body_text="Hello {{ first_name }}",
            recipient_season=self.season,
        )
        self.scheduled.practices.set(self.practices)
        self.scheduled.sync_mentor_tokens()
        self.token_row = ScheduledEmailMentorToken.objects.get(
            scheduled_email=self.scheduled,
            mentor=self.mentor,
        )

    def test_put_saves_replies_linked_to_mentor(self):
        url = f"/api/mentor-email-reply/{self.token_row.token}/"
        payload = {
            "replies": [
                {
                    "practice": p.id,
                    "attendance": PracticeAttendanceReply.ATTENDING,
                    "pace": "",
                }
                for p in self.practices
            ],
        }

        response = self.client.put(url, payload, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["saved"], 4)
        self.assertEqual(response.data["mentor_id"], self.mentor.id)
        stored = ScheduledEmailMentorPracticeReply.objects.filter(
            mentor=self.mentor,
            mentor_token=self.token_row,
        )
        self.assertEqual(stored.count(), 4)
        attending = stored.filter(
            attendance=PracticeAttendanceReply.ATTENDING
        ).count()
        self.assertEqual(attending, 4)
        self.practices[0].refresh_from_db()
        assignment = MentorPracticeAssignment.objects.get(
            mentor=self.mentor,
            practice=self.practices[0],
        )
        self.assertEqual(assignment.pace, "11-12")
        self.assertIn(
            self.mentor.id,
            list(self.practices[0].mentors.values_list("pk", flat=True)),
        )

    def test_get_returns_saved_replies(self):
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=self.token_row,
            mentor=self.mentor,
            practice=self.practices[0],
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="",
        )
        url = f"/api/mentor-email-reply/{self.token_row.token}/"

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        practice = next(
            p for p in response.data["practices"] if p["id"] == self.practices[0].id
        )
        self.assertEqual(practice["attendance"], PracticeAttendanceReply.ATTENDING)

    def test_practice_mentor_replies_uses_latest_per_mentor(self):
        other_email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() + timedelta(days=14),
            body_text="Follow up",
            recipient_season=self.season,
        )
        other_email.practices.set(self.practices)
        other_email.sync_mentor_tokens()
        other_token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=other_email,
            mentor=self.mentor,
        )
        older = ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=self.token_row,
            mentor=self.mentor,
            practice=self.practices[0],
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="10-11",
        )
        newer = ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=other_token,
            mentor=self.mentor,
            practice=self.practices[0],
            attendance=PracticeAttendanceReply.FIRST_HALF,
            pace="11-12",
        )
        ScheduledEmailMentorPracticeReply.objects.filter(pk=older.pk).update(
            updated_at=timezone.now() - timedelta(hours=2)
        )
        ScheduledEmailMentorPracticeReply.objects.filter(pk=newer.pk).update(
            updated_at=timezone.now() - timedelta(hours=1)
        )
        url = f"/api/practice/{self.practices[0].id}/mentor-replies/"

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["attendance"], PracticeAttendanceReply.FIRST_HALF)
        self.assertEqual(response.data[0]["pace"], "11-12")
