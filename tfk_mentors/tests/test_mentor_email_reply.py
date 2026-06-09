from datetime import timedelta

from django.db.models import Prefetch
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

    def test_reply_stats_counts_full_responses(self):
        self.assertEqual(
            self.scheduled.reply_stats(),
            {
                "mentors_emailed": 1,
                "mentors_replied": 0,
                "mentors_selected_practices": 0,
                "mentors_responded": 0,
                "mentors_pending": 1,
            },
        )
        for practice in self.practices:
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=self.token_row,
                mentor=self.mentor,
                practice=practice,
                attendance=PracticeAttendanceReply.ATTENDING,
                pace="",
            )
        self.assertEqual(
            self.scheduled.reply_stats(),
            {
                "mentors_emailed": 1,
                "mentors_replied": 1,
                "mentors_selected_practices": 1,
                "mentors_responded": 1,
                "mentors_pending": 0,
            },
        )

    def test_reply_stats_counts_partial_reply(self):
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=self.token_row,
            mentor=self.mentor,
            practice=self.practices[0],
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="",
        )
        stats = self.scheduled.reply_stats()
        self.assertEqual(stats["mentors_replied"], 1)
        self.assertEqual(stats["mentors_selected_practices"], 1)
        self.assertEqual(stats["mentors_pending"], 0)

    def test_reply_stats_replied_without_selecting_practices(self):
        for practice in self.practices:
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=self.token_row,
                mentor=self.mentor,
                practice=practice,
                attendance=PracticeAttendanceReply.NOT_ATTENDING,
                pace="",
            )
        self.assertEqual(
            self.scheduled.reply_stats(),
            {
                "mentors_emailed": 1,
                "mentors_replied": 1,
                "mentors_selected_practices": 0,
                "mentors_responded": 1,
                "mentors_pending": 0,
            },
        )

    def test_reply_stats_counts_mentor_assignments_without_reply_rows(self):
        self.scheduled.task_completed_at = timezone.now()
        self.scheduled.save(update_fields=["task_completed_at"])
        MentorPracticeAssignment.objects.create(
            mentor=self.mentor,
            practice=self.practices[0],
            pace="11-12",
        )

        stats = self.scheduled.reply_stats()
        self.assertEqual(stats["mentors_replied"], 1)
        self.assertEqual(stats["mentors_selected_practices"], 1)

    def test_reply_stats_finds_practices_without_email_m2m_link(self):
        self.scheduled.task_completed_at = timezone.now()
        self.scheduled.practices.clear()
        self.scheduled.save(update_fields=["task_completed_at"])
        MentorPracticeAssignment.objects.create(
            mentor=self.mentor,
            practice=self.practices[0],
            pace="11-12",
        )

        stats = self.scheduled.reply_stats()
        self.assertEqual(stats["mentors_replied"], 1)

    def test_reply_stats_counts_replies_on_linked_practices_from_other_email_token(self):
        """Replies saved under a newer email's token still count for the earlier send."""
        older_sent = self.scheduled
        older_sent.task_completed_at = timezone.now() - timedelta(days=7)
        older_sent.save(update_fields=["task_completed_at"])

        newer_send = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() + timedelta(days=7),
            body_text="Follow up",
            recipient_season=self.season,
        )
        newer_send.practices.set(self.practices)
        newer_send.sync_mentor_tokens()
        newer_token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=newer_send,
            mentor=self.mentor,
        )
        for practice in self.practices:
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=newer_token,
                mentor=self.mentor,
                practice=practice,
                attendance=PracticeAttendanceReply.ATTENDING,
                pace="11-12",
            )

        stats = older_sent.reply_stats()
        self.assertEqual(stats["mentors_replied"], 1)
        self.assertEqual(stats["mentors_selected_practices"], 1)
        self.assertEqual(stats["mentors_pending"], 0)

    def test_reply_stats_ignores_stale_prefetched_tokens(self):
        for practice in self.practices:
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=self.token_row,
                mentor=self.mentor,
                practice=practice,
                attendance=PracticeAttendanceReply.ATTENDING,
                pace="",
            )
        scheduled = (
            ScheduledEmail.objects.prefetch_related(
                Prefetch(
                    "mentor_tokens",
                    queryset=ScheduledEmailMentorToken.objects.none(),
                )
            )
            .get(pk=self.scheduled.pk)
        )
        stats = scheduled.reply_stats()
        self.assertEqual(stats["mentors_replied"], 1)
        self.assertEqual(stats["mentors_selected_practices"], 1)

    def test_scheduled_email_api_includes_reply_stats(self):
        self.scheduled.task_completed_at = timezone.now()
        self.scheduled.save(update_fields=["task_completed_at"])
        for practice in self.practices:
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=self.token_row,
                mentor=self.mentor,
                practice=practice,
                attendance=PracticeAttendanceReply.ATTENDING,
                pace="",
            )

        response = self.client.get("/api/scheduled-email/")

        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.data if item["id"] == self.scheduled.id)
        self.assertEqual(
            row["reply_stats"],
            {
                "mentors_emailed": 1,
                "mentors_replied": 1,
                "mentors_selected_practices": 1,
                "mentors_responded": 1,
                "mentors_pending": 0,
            },
        )
