from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import (
    Mentor,
    MentorTypes,
    Practice,
    ScheduledEmail,
    ScheduledEmailMentorToken,
    Season,
)


class ScheduledEmailListLeanTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()
        self.season = Season.objects.create(year=2026, is_current=True)
        self.mentor = Mentor.objects.create(
            first_name="Pat",
            last_name="Pending",
            email="pat@example.com",
            type=MentorTypes.PRACTICE,
            pace="8",
        )
        self.mentor.seasons.add(self.season)
        self.email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() - timedelta(days=1),
            task_completed_at=timezone.now() - timedelta(hours=1),
            body_text="Hello {{first_name}}",
            recipient_mode="all_in_season",
            recipient_season=self.season,
            recipients_emailed_count=1,
        )
        ScheduledEmailMentorToken.objects.create(
            scheduled_email=self.email,
            mentor=self.mentor,
            included_in_send=True,
        )

    def test_list_uses_summary_stats_without_pending_mentor_rows(self):
        response = self.client.get("/api/scheduled-email/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        row = response.data[0]
        self.assertNotIn("pending_mentors", row)
        stats = row["reply_stats"]
        self.assertEqual(stats["mentors_emailed"], 1)
        self.assertEqual(stats["mentors_pending"], 1)
        self.assertEqual(stats["pending_mentor_ids"], [self.mentor.id])
        self.assertNotIn("pending_mentors", stats)

    def test_detail_still_includes_pending_mentors(self):
        response = self.client.get(f"/api/scheduled-email/{self.email.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("pending_mentors", response.data)
        self.assertEqual(response.data["pending_mentors"][0]["id"], self.mentor.id)
