from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import override_settings
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

    @override_settings(DEBUG=True)
    def test_list_reply_stats_query_count_is_bounded(self):
        mentors = []
        for index in range(8):
            mentor = Mentor.objects.create(
                first_name=f"M{index}",
                last_name="Bulk",
                email=f"bulk{index}@example.com",
                type=MentorTypes.PRACTICE,
                pace="8",
            )
            mentor.seasons.add(self.season)
            mentors.append(mentor)

        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=30),
            season=self.season,
        )
        created_ids = []
        for index in range(10):
            email = ScheduledEmail.objects.create(
                scheduled_send_at=timezone.now() - timedelta(days=index + 2),
                task_completed_at=timezone.now() - timedelta(days=index + 1),
                body_text=f"Hello {index}",
                recipient_mode="all_in_season",
                recipient_season=self.season,
                recipients_emailed_count=2,
            )
            created_ids.append(email.id)
            token_a = ScheduledEmailMentorToken.objects.create(
                scheduled_email=email,
                mentor=mentors[index % len(mentors)],
                included_in_send=True,
            )
            ScheduledEmailMentorToken.objects.create(
                scheduled_email=email,
                mentor=mentors[(index + 1) % len(mentors)],
                included_in_send=True,
            )
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=token_a,
                mentor=token_a.mentor,
                practice=practice,
                attendance=PracticeAttendanceReply.ATTENDING,
                pace="8",
            )

        connection.queries_log.clear()
        response = self.client.get("/api/scheduled-email/")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data), 11)
        # Prefetch + one replies query should keep this far below O(emails * 4+).
        self.assertLess(len(connection.queries), 30)
        row = next(item for item in response.data if item["id"] in created_ids)
        self.assertEqual(row["reply_stats"]["mentors_emailed"], 2)
        self.assertEqual(row["reply_stats"]["mentors_replied"], 1)
        self.assertEqual(row["reply_stats"]["mentors_pending"], 1)
        self.assertEqual(row["reply_stats"]["mentors_selected_practices"], 1)
