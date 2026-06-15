from datetime import timedelta
from unittest.mock import patch

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


def mark_email_sent(email, *, completed_at=None):
    """Test helper: freeze recipients for a sent email."""
    if completed_at is not None:
        email.task_completed_at = completed_at
    elif email.task_completed_at is None:
        email.task_completed_at = timezone.now()
    email.mark_sent_recipients()
    email.save(
        update_fields=[
            "task_completed_at",
            "recipients_emailed_count",
            "updated_at",
        ]
    )
    return email


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

    def test_remote_mentor_reply_saves_profile_and_practice_pace(self):
        self.mentor.type = MentorTypes.REMOTE
        self.mentor.pace = ""
        self.mentor.save(update_fields=["type", "pace"])
        url = f"/api/mentor-email-reply/{self.token_row.token}/"
        payload = {
            "email_received_confirmed": True,
            "mentor_pace": "10-11",
            "replies": [
                {
                    "practice": self.practices[0].id,
                    "attendance": PracticeAttendanceReply.ATTENDING,
                    "pace": "",
                },
                {
                    "practice": self.practices[1].id,
                    "attendance": PracticeAttendanceReply.NOT_ATTENDING,
                    "pace": "",
                },
                {
                    "practice": self.practices[2].id,
                    "attendance": PracticeAttendanceReply.ATTENDING,
                    "pace": "",
                },
                {
                    "practice": self.practices[3].id,
                    "attendance": PracticeAttendanceReply.NOT_ATTENDING,
                    "pace": "",
                },
            ],
        }

        response = self.client.put(url, payload, format="json")

        self.assertEqual(response.status_code, 200)
        self.mentor.refresh_from_db()
        self.assertEqual(self.mentor.pace, "10-11")
        attending = ScheduledEmailMentorPracticeReply.objects.filter(
            mentor_token=self.token_row,
            attendance=PracticeAttendanceReply.ATTENDING,
        )
        self.assertEqual(attending.count(), 2)
        for reply in attending:
            self.assertEqual(reply.pace, "10-11")
        assignment = MentorPracticeAssignment.objects.get(
            mentor=self.mentor,
            practice=self.practices[0],
        )
        self.assertEqual(assignment.pace, "10-11")

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
        self.assertEqual(len(response.data["mentors"]), 1)
        self.assertEqual(response.data["mentors"][0]["attendance"], PracticeAttendanceReply.FIRST_HALF)
        self.assertEqual(response.data["mentors"][0]["pace"], "11-12")

    def test_reply_stats_counts_full_responses(self):
        stats = self.scheduled.reply_stats()
        self.assertEqual(stats["mentors_emailed"], 1)
        self.assertEqual(stats["mentors_replied"], 0)
        self.assertEqual(stats["mentors_pending"], 1)
        self.assertEqual(stats["pending_mentor_ids"], [self.mentor.id])
        self.assertEqual(len(stats["pending_mentors"]), 1)
        self.assertEqual(stats["pending_mentors"][0]["email"], self.mentor.email)

        for practice in self.practices:
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=self.token_row,
                mentor=self.mentor,
                practice=practice,
                attendance=PracticeAttendanceReply.ATTENDING,
                pace="",
            )
        stats = self.scheduled.reply_stats()
        self.assertEqual(stats["mentors_replied"], 1)
        self.assertEqual(stats["mentors_pending"], 0)
        self.assertEqual(stats["pending_mentor_ids"], [])
        self.assertEqual(stats["pending_mentors"], [])

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
        stats = self.scheduled.reply_stats()
        self.assertEqual(stats["mentors_replied"], 1)
        self.assertEqual(stats["mentors_selected_practices"], 0)
        self.assertEqual(stats["mentors_pending"], 0)
        self.assertEqual(stats["pending_mentor_ids"], [])
        self.assertEqual(stats["pending_mentors"], [])

    def test_reply_stats_ignores_mentor_assignments_without_reply_rows(self):
        self.scheduled.task_completed_at = timezone.now()
        mark_email_sent(self.scheduled)
        MentorPracticeAssignment.objects.create(
            mentor=self.mentor,
            practice=self.practices[0],
            pace="11-12",
        )

        stats = self.scheduled.reply_stats()
        self.assertEqual(stats["mentors_replied"], 0)
        self.assertEqual(stats["mentors_selected_practices"], 0)
        self.assertEqual(stats["mentors_pending"], 1)

    def test_reply_stats_ignores_assignments_without_email_m2m_link(self):
        self.scheduled.task_completed_at = timezone.now()
        self.scheduled.practices.clear()
        mark_email_sent(self.scheduled)
        MentorPracticeAssignment.objects.create(
            mentor=self.mentor,
            practice=self.practices[0],
            pace="11-12",
        )

        stats = self.scheduled.reply_stats()
        self.assertEqual(stats["mentors_replied"], 0)
        self.assertEqual(stats["mentors_pending"], 1)

    def test_reply_stats_scoped_to_each_sent_email(self):
        """Replies under a newer email's token do not count toward an earlier send."""
        older_sent = self.scheduled
        mark_email_sent(older_sent, completed_at=timezone.now() - timedelta(days=7))

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

        older_stats = older_sent.reply_stats()
        self.assertEqual(older_stats["mentors_replied"], 0)
        self.assertEqual(older_stats["mentors_selected_practices"], 0)
        self.assertEqual(older_stats["mentors_pending"], 1)

        mark_email_sent(newer_send)
        newer_stats = newer_send.reply_stats()
        self.assertEqual(newer_stats["mentors_replied"], 1)
        self.assertEqual(newer_stats["mentors_selected_practices"], 1)
        self.assertEqual(newer_stats["mentors_pending"], 0)

    def test_pending_mentor_lists_differ_per_sent_email(self):
        """Each sent email exposes its own awaiting mentors on list and detail APIs."""
        mentor_b = Mentor.objects.create(
            first_name="Quinn",
            last_name="Pending",
            email="quinn@example.com",
            cell_phone="555-0101",
            type=MentorTypes.PRACTICE,
            pace="10-11",
            split_practice=False,
        )
        mentor_b.seasons.add(self.season)

        first_send = self.scheduled
        mark_email_sent(first_send, completed_at=timezone.now() - timedelta(days=14))
        for practice in self.practices:
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=self.token_row,
                mentor=self.mentor,
                practice=practice,
                attendance=PracticeAttendanceReply.ATTENDING,
                pace="11-12",
            )

        second_send = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() - timedelta(days=7),
            body_text="Follow up",
            recipient_season=self.season,
        )
        second_send.practices.set(self.practices)
        second_send.sync_mentor_tokens()
        mark_email_sent(second_send, completed_at=timezone.now() - timedelta(days=7))

        first_stats = first_send.reply_stats()
        second_stats = second_send.reply_stats()
        self.assertEqual(first_stats["mentors_pending"], 0)
        self.assertEqual(first_stats["pending_mentors"], [])
        self.assertEqual(second_stats["mentors_pending"], 2)
        second_pending_emails = {
            row["email"] for row in second_stats["pending_mentors"]
        }
        self.assertEqual(
            second_pending_emails,
            {self.mentor.email, mentor_b.email},
        )

        response = self.client.get("/api/scheduled-email/")
        self.assertEqual(response.status_code, 200)
        rows_by_id = {row["id"]: row for row in response.data}
        first_row = rows_by_id[first_send.id]
        second_row = rows_by_id[second_send.id]
        self.assertEqual(first_row["reply_stats"]["mentors_pending"], 0)
        self.assertEqual(first_row["pending_mentors"], [])
        self.assertEqual(second_row["reply_stats"]["mentors_pending"], 2)
        self.assertEqual(
            {row["email"] for row in second_row["pending_mentors"]},
            {self.mentor.email, mentor_b.email},
        )
        self.assertEqual(
            {row["email"] for row in second_row["reply_stats"]["pending_mentors"]},
            {self.mentor.email, mentor_b.email},
        )

        pending_response = self.client.get(
            f"/api/scheduled-email/{second_send.id}/pending-mentors/"
        )
        self.assertEqual(pending_response.status_code, 200)
        self.assertEqual(
            {row["email"] for row in pending_response.data["pending_mentors"]},
            {self.mentor.email, mentor_b.email},
        )

    @patch("tfk_mentors.email_sending.send_mail")
    def test_emailed_count_frozen_at_send_for_all_in_season(self, mock_send_mail):
        """Mentors added to the season after send are not counted as emailed."""
        mock_send_mail.return_value = 1
        send_at = timezone.now() - timedelta(days=3)
        self.scheduled.task_completed_at = None
        self.scheduled.recipients_emailed_count = None
        self.scheduled.save(
            update_fields=["task_completed_at", "recipients_emailed_count"]
        )

        from tfk_mentors.email_sending import send_scheduled_email

        send_scheduled_email(self.scheduled)
        self.scheduled.refresh_from_db()
        self.assertEqual(self.scheduled.recipients_emailed_count, 1)

        mentor_b = Mentor.objects.create(
            first_name="Later",
            last_name="Joiner",
            email="later@example.com",
            cell_phone="555-0199",
            type=MentorTypes.PRACTICE,
            pace="10-11",
            split_practice=False,
        )
        mentor_b.seasons.add(self.season)
        self.scheduled.sync_mentor_tokens()
        self.scheduled.save(update_fields=["body_text"])

        stats = self.scheduled.reply_stats()
        self.assertEqual(stats["mentors_emailed"], 1)
        self.assertEqual(stats["mentors_pending"], 1)
        self.assertEqual(len(stats["pending_mentors"]), 1)
        self.assertEqual(stats["pending_mentors"][0]["email"], self.mentor.email)

        response = self.client.get("/api/scheduled-email/")
        row = next(item for item in response.data if item["id"] == self.scheduled.id)
        self.assertEqual(row["recipients_emailed_count"], 1)
        self.assertEqual(row["reply_stats"]["mentors_emailed"], 1)

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
        mark_email_sent(self.scheduled)
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
        stats = row["reply_stats"]
        self.assertEqual(stats["mentors_emailed"], 1)
        self.assertEqual(stats["mentors_replied"], 1)
        self.assertEqual(stats["mentors_selected_practices"], 1)
        self.assertEqual(stats["mentors_pending"], 0)
        self.assertEqual(stats["pending_mentor_ids"], [])
        self.assertEqual(stats["pending_mentors"], [])


class ReplyReminderTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()
        self.season = Season.objects.create(year=2026)
        self.replied_mentor = Mentor.objects.create(
            first_name="Pat",
            last_name="Replied",
            email="pat@example.com",
            cell_phone="555-0100",
            type=MentorTypes.PRACTICE,
            pace="11-12",
            split_practice=False,
        )
        self.pending_mentor = Mentor.objects.create(
            first_name="Sam",
            last_name="Pending",
            email="sam@example.com",
            cell_phone="555-0101",
            type=MentorTypes.PRACTICE,
            pace="10-11",
            split_practice=False,
        )
        for mentor in (self.replied_mentor, self.pending_mentor):
            mentor.seasons.add(self.season)
        now = timezone.now()
        self.practices = [
            Practice.objects.create(
                date=now + timedelta(days=offset),
                season=self.season,
                full_practice=True,
            )
            for offset in (1, 2)
        ]
        self.scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=now - timedelta(days=1),
            body_text="Hello {{ first_name }}",
            recipient_season=self.season,
        )
        self.scheduled.practices.set(self.practices)
        self.scheduled.sync_mentor_tokens()
        mark_email_sent(self.scheduled, completed_at=now)
        self.replied_token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=self.scheduled,
            mentor=self.replied_mentor,
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=self.replied_token,
            mentor=self.replied_mentor,
            practice=self.practices[0],
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="11-12",
        )

    def test_pending_mentors_for_reminder_excludes_replied(self):
        pending = list(self.scheduled.pending_mentors_for_reminder())
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].id, self.pending_mentor.id)

    def test_scheduled_email_api_includes_pending_mentors(self):
        response = self.client.get(
            f"/api/scheduled-email/{self.scheduled.id}/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["pending_mentors"]), 1)
        pending_row = response.data["pending_mentors"][0]
        self.assertEqual(pending_row["email"], self.pending_mentor.email)
        self.assertEqual(pending_row["first_name"], self.pending_mentor.first_name)
        self.assertEqual(pending_row["last_name"], self.pending_mentor.last_name)
        self.assertEqual(pending_row["name"], f"{self.pending_mentor.first_name} {self.pending_mentor.last_name}")
        stats = response.data["reply_stats"]
        self.assertEqual(stats["mentors_pending"], 1)
        self.assertEqual(len(stats["pending_mentors"]), 1)
        self.assertEqual(stats["pending_mentors"][0]["email"], self.pending_mentor.email)

    def test_scheduled_email_pending_mentors_endpoint(self):
        response = self.client.get(
            f"/api/scheduled-email/{self.scheduled.id}/pending-mentors/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["pending_mentors"]), 1)
        self.assertEqual(
            response.data["pending_mentors"][0]["email"],
            self.pending_mentor.email,
        )

    def test_render_reminder_body_includes_availability_message_and_link(self):
        body = self.scheduled.render_reminder_body_for_mentor(self.pending_mentor)
        self.assertIn("At Practice mentors must reply with their availability.", body)
        link = self.scheduled.reply_absolute_url_for_mentor(self.pending_mentor)
        self.assertIn(link, body)

    @patch("tfk_mentors.email_sending.send_mail")
    def test_send_reply_reminders_only_emails_pending(self, mock_send_mail):
        from tfk_mentors.email_sending import send_reply_reminders

        result = send_reply_reminders(self.scheduled)

        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["recipients"], 1)
        self.assertEqual(mock_send_mail.call_count, 1)
        _, kwargs = mock_send_mail.call_args
        self.assertEqual(kwargs["recipient_list"], [self.pending_mentor.email])
        self.assertIn(
            "At Practice mentors must reply with their availability.",
            kwargs["message"],
        )
        self.assertIn("/mentor-reply?token=", kwargs["message"])

    @patch("tfk_mentors.email_sending.send_mail")
    def test_api_send_reply_reminders(self, mock_send_mail):
        response = self.client.post(
            f"/api/scheduled-email/{self.scheduled.id}/send-reply-reminders/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["sent"], 1)
        self.assertEqual(mock_send_mail.call_count, 1)

    def test_api_send_reply_reminders_dry_run_includes_pending_mentors(self):
        response = self.client.post(
            f"/api/scheduled-email/{self.scheduled.id}/send-reply-reminders/",
            {"dry_run": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["recipients"], 1)
        self.assertEqual(len(response.data["pending_mentors"]), 1)
        self.assertEqual(
            response.data["pending_mentors"][0]["email"],
            self.pending_mentor.email,
        )

    def test_api_send_reply_reminders_requires_sent_email(self):
        unsent = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() + timedelta(days=1),
            body_text="Hello",
            recipient_season=self.season,
        )
        unsent.practices.set(self.practices)

        response = self.client.post(
            f"/api/scheduled-email/{unsent.id}/send-reply-reminders/"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("sent", response.data["detail"].lower())


class SendScheduledEmailNowTests(TestCase):
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
        self.scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=now + timedelta(days=7),
            body_text="Hello {{ first_name }} {{ link }}",
            recipient_season=self.season,
        )

    @patch("tfk_mentors.email_sending.send_mail")
    def test_api_send_now_emails_mentors(self, mock_send_mail):
        response = self.client.post(
            f"/api/scheduled-email/{self.scheduled.id}/send-now/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["sent"], 1)
        self.assertEqual(mock_send_mail.call_count, 1)
        self.scheduled.refresh_from_db()
        self.assertIsNotNone(self.scheduled.task_completed_at)

    def test_api_send_now_rejects_already_sent(self):
        self.scheduled.task_completed_at = timezone.now()
        self.scheduled.save(update_fields=["task_completed_at"])

        response = self.client.post(
            f"/api/scheduled-email/{self.scheduled.id}/send-now/"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("already been sent", response.data["detail"].lower())


class BulkEmailReplyStatsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()
        self.season = Season.objects.create(year=2026)
        now = timezone.now()
        self.practices = [
            Practice.objects.create(
                date=now + timedelta(days=offset),
                season=self.season,
                full_practice=True,
            )
            for offset in (1, 2, 3, 4)
        ]
        self.mentors = [
            Mentor.objects.create(
                first_name=f"M{i}",
                last_name=f"Test{i}",
                email=f"mentor{i}@example.com",
                cell_phone=f"555-01{i:02d}",
                type=MentorTypes.PRACTICE,
                pace="11-12",
                split_practice=False,
            )
            for i in range(62)
        ]
        for mentor in self.mentors:
            mentor.seasons.add(self.season)
        self.scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=now - timedelta(days=1),
            body_text="Hello {{ first_name }} {{ link }}",
            recipient_season=self.season,
        )
        self.scheduled.practices.set(self.practices)
        self.scheduled.sync_mentor_tokens()
        mark_email_sent(self.scheduled, completed_at=now)

    def test_reply_stats_for_bulk_season_send(self):
        replying = self.mentors[:14]
        for mentor in replying:
            token = ScheduledEmailMentorToken.objects.get(
                scheduled_email=self.scheduled,
                mentor=mentor,
            )
            for practice in self.practices:
                ScheduledEmailMentorPracticeReply.objects.create(
                    mentor_token=token,
                    mentor=mentor,
                    practice=practice,
                    attendance=PracticeAttendanceReply.ATTENDING,
                    pace="11-12",
                )

        stats = self.scheduled.reply_stats()
        self.assertEqual(stats["mentors_emailed"], 62)
        self.assertEqual(stats["mentors_replied"], 14)
        self.assertEqual(stats["mentors_selected_practices"], 14)
        self.assertEqual(stats["mentors_pending"], 48)

        response = self.client.get("/api/scheduled-email/")
        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.data if item["id"] == self.scheduled.id)
        self.assertEqual(row["reply_stats"]["mentors_replied"], 14)

    def test_scheduled_email_detail_includes_pending_mentors_for_bulk_send(self):
        replying = self.mentors[:60]
        for mentor in replying:
            token = ScheduledEmailMentorToken.objects.get(
                scheduled_email=self.scheduled,
                mentor=mentor,
            )
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=token,
                mentor=mentor,
                practice=self.practices[0],
                attendance=PracticeAttendanceReply.ATTENDING,
                pace="11-12",
            )

        response = self.client.get(f"/api/scheduled-email/{self.scheduled.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["reply_stats"]["mentors_replied"], 60)
        self.assertEqual(response.data["reply_stats"]["mentors_pending"], 2)
        self.assertEqual(len(response.data["reply_stats"]["pending_mentor_ids"]), 2)
        self.assertEqual(len(response.data["reply_stats"]["pending_mentors"]), 2)
        self.assertEqual(len(response.data["pending_mentors"]), 2)
        pending_emails = {row["email"] for row in response.data["pending_mentors"]}
        expected_emails = {
            self.mentors[60].email,
            self.mentors[61].email,
        }
        self.assertEqual(pending_emails, expected_emails)

    def test_reply_stats_counts_token_replies_without_recipient_season(self):
        """Replies still count if recipient season was cleared after send."""
        replying = self.mentors[:3]
        for mentor in replying:
            token = ScheduledEmailMentorToken.objects.get(
                scheduled_email=self.scheduled,
                mentor=mentor,
            )
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=token,
                mentor=mentor,
                practice=self.practices[0],
                attendance=PracticeAttendanceReply.ATTENDING,
                pace="11-12",
            )
        self.scheduled.recipient_season = None
        self.scheduled.save(update_fields=["recipient_season"])

        stats = self.scheduled.reply_stats()
        self.assertEqual(stats["mentors_replied"], 3)
        self.assertGreaterEqual(stats["mentors_emailed"], 3)
