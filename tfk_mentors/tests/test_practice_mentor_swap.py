from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import (
    Coach,
    Mentor,
    MentorPracticeAssignment,
    MentorPracticeShowUp,
    MentorTypes,
    PaceTypes,
    Practice,
    PracticeAttendanceReply,
    PracticeReminderEmail,
    PracticeReminderKind,
    PracticeReminderRecipientKind,
    ScheduledEmail,
    ScheduledEmailMentorPracticeReply,
    ScheduledEmailMentorToken,
    Season,
    ShowUpStatus,
)
from tfk_mentors.practice_reminder import (
    ReminderRecipient,
    build_practice_section,
    collect_recipients,
    mentor_schedule_notice,
    render_reminder_for_recipient,
    sync_practice_reminders_for_season,
)


class PracticeMentorSwapTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

        self._email_patcher = patch(
            "tfk_mentors.practice_swap_notification._verify_email_delivery"
        )
        self._email_patcher.start()
        self.addCleanup(self._email_patcher.stop)

        self.season = Season.objects.create(year=2026)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=3),
            season=self.season,
            full_practice=True,
        )
        self.outgoing = Mentor.objects.create(
            first_name="Out",
            last_name="Going",
            email="out@example.com",
            cell_phone="555-0100",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.TEN.value,
        )
        self.incoming = Mentor.objects.create(
            first_name="In",
            last_name="Coming",
            email="in@example.com",
            cell_phone="555-0101",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.EIGHT.value,
        )
        self.outgoing.seasons.add(self.season)
        self.incoming.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=self.outgoing,
            practice=self.practice,
            pace=self.outgoing.pace,
            is_available=False,
        )
        self.practice.mentors.add(self.outgoing)

    def test_swap_replaces_mentor_and_records_found_replacement(self):
        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["outgoing_mentor_id"], self.outgoing.id)
        self.assertEqual(response.data["show_up"], ShowUpStatus.FOUND_REPLACEMENT)
        self.assertIsNone(response.data["coach_notification"])
        self.assertEqual(response.data["mentor_confirmations"]["sent"], 2)

        self.practice.refresh_from_db()
        self.assertNotIn(self.outgoing, self.practice.mentors.all())
        self.assertIn(self.incoming, self.practice.mentors.all())
        show_up = MentorPracticeShowUp.objects.get(
            mentor=self.outgoing,
            practice=self.practice,
        )
        self.assertEqual(show_up.show_up, ShowUpStatus.FOUND_REPLACEMENT)

    def test_swap_sends_confirmation_emails_to_both_mentors(self):
        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)
        recipients = {tuple(message.to) for message in mail.outbox}
        self.assertEqual(
            recipients,
            {(self.outgoing.email,), (self.incoming.email,)},
        )
        for message in mail.outbox:
            self.assertEqual(message.subject, "TFK Mentor Swap Confirmation")
            self.assertIn(
                "Out Going has been replaced with In Coming",
                message.body,
            )
            self.assertIn(
                "If this was made in error please reply to this email.",
                message.body,
            )

    def test_attendance_payload_includes_swapped_out_mentor(self):
        self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        response = self.client.get(f"/api/practice-attendance/{self.practice.id}/")
        self.assertEqual(response.status_code, 200)
        mentors = response.data["assigned_mentors"]
        swapped = next(
            row for row in mentors if row["mentor_id"] == self.outgoing.id
        )
        self.assertTrue(swapped["swapped_out"])
        self.assertEqual(swapped["show_up"], ShowUpStatus.FOUND_REPLACEMENT)

    def test_archived_attendance_counts_found_replacement(self):
        self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.practice.date = timezone.now() - timedelta(days=2)
        self.practice.save(update_fields=["date", "updated_at"])

        response = self.client.get("/api/practice-attendance/archived/")
        self.assertEqual(response.status_code, 200)
        row = next(
            item for item in response.data if item["practice_id"] == self.practice.id
        )
        self.assertEqual(row["found_replacement_count"], 1)
        self.assertEqual(row["assigned_count"], 1)

    def test_swap_rejects_incoming_mentor_already_on_practice(self):
        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.outgoing.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_swap_allows_incoming_mentor_marked_available(self):
        available = Mentor.objects.create(
            first_name="Avail",
            last_name="Able",
            email="avail@example.com",
            cell_phone="555-0102",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        available.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=available,
            practice=self.practice,
            pace=available.pace,
            is_available=True,
        )

        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": available.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["incoming_mentor"]["mentor_id"], available.id)

        self.practice.refresh_from_db()
        self.assertNotIn(self.outgoing, self.practice.mentors.all())
        self.assertIn(available, self.practice.mentors.all())
        self.assertFalse(
            MentorPracticeAssignment.objects.filter(
                mentor=available,
                practice=self.practice,
                is_available=True,
            ).exists()
        )

    def _mark_last_reminder_sent(self, practice):
        Practice.objects.create(
            date=practice.date - timedelta(days=7),
            season=self.season,
            full_practice=True,
        )
        sync_practice_reminders_for_season(self.season)
        reminder = PracticeReminderEmail.objects.get(
            practice_one=practice,
            kind=PracticeReminderKind.AFTER_PRACTICE,
        )
        reminder.task_completed_at = timezone.now()
        reminder.save(update_fields=["task_completed_at"])
        return reminder

    def test_swap_emails_coaches_after_last_reminder_sent(self):
        coach = Coach.objects.create(
            first_name="Casey",
            last_name="Coach",
            email="casey@example.com",
            cell="555-0200",
        )
        coach.seasons.add(self.season)

        head_coach = Coach.objects.create(
            first_name="Head",
            last_name="Coach",
            email="head@example.com",
        )
        head_coach.seasons.add(self.season)
        self.season.head_coach = head_coach
        self.season.save(update_fields=["head_coach"])

        other_coach = Coach.objects.create(
            first_name="Other",
            last_name="Season",
            email="other@example.com",
        )
        other_coach.seasons.add(self.season)

        outside = Coach.objects.create(
            first_name="Out",
            last_name="Side",
            email="outside@example.com",
        )
        outside_season = Season.objects.create(year=2025)
        outside.seasons.add(outside_season)

        self._mark_last_reminder_sent(self.practice)

        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["mentor_confirmations"]["sent"], 2)
        self.assertEqual(response.data["coach_notification"]["sent"], 1)
        self.assertEqual(response.data["coach_notification"]["recipients"], 3)
        self.assertEqual(len(mail.outbox), 3)

        mentor_messages = [
            message
            for message in mail.outbox
            if message.subject == "TFK Mentor Swap Confirmation"
        ]
        coach_messages = [
            message
            for message in mail.outbox
            if message.subject.startswith("Mentor swap for TFK practice")
        ]
        self.assertEqual(len(mentor_messages), 2)
        self.assertEqual(len(coach_messages), 1)
        self.assertCountEqual(
            coach_messages[0].to,
            [coach.email, head_coach.email, other_coach.email],
        )
        self.assertNotIn(outside.email, coach_messages[0].to)
        self.assertIn("In Coming is replacing Out Going", coach_messages[0].body)
        self.assertIn(PaceTypes.TEN.value, coach_messages[0].body)
        self.assertIn("555-0101", coach_messages[0].body)

    def test_swap_does_not_duplicate_head_coach_also_in_season(self):
        head_coach = Coach.objects.create(
            first_name="Head",
            last_name="Coach",
            email="head@example.com",
        )
        head_coach.seasons.add(self.season)
        self.season.head_coach = head_coach
        self.season.save(update_fields=["head_coach"])
        self._mark_last_reminder_sent(self.practice)

        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["coach_notification"]["sent"], 1)
        self.assertEqual(response.data["coach_notification"]["recipients"], 1)
        coach_messages = [
            message
            for message in mail.outbox
            if message.subject.startswith("Mentor swap for TFK practice")
        ]
        self.assertEqual(len(coach_messages), 1)
        self.assertEqual(coach_messages[0].to, [head_coach.email])

    def test_swap_skips_coach_email_when_reminder_not_sent(self):
        coach = Coach.objects.create(
            first_name="Casey",
            last_name="Coach",
            email="casey@example.com",
        )
        coach.seasons.add(self.season)

        Practice.objects.create(
            date=self.practice.date - timedelta(days=7),
            season=self.season,
            full_practice=True,
        )
        sync_practice_reminders_for_season(self.season)
        reminder = PracticeReminderEmail.objects.get(practice_one=self.practice)
        self.assertIsNone(reminder.task_completed_at)

        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["coach_notification"])
        self.assertEqual(response.data["mentor_confirmations"]["sent"], 2)
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(
            all(
                message.subject == "TFK Mentor Swap Confirmation"
                for message in mail.outbox
            )
        )

    def test_practice_reminder_lists_swapped_in_mentor_not_outgoing(self):
        """Reminder roster and schedule notice follow the post-swap assignment."""
        earlier = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=self.season,
            full_practice=True,
            description="Earlier practice",
        )
        self.practice.description = "Target practice"
        self.practice.save(update_fields=["description", "updated_at"])

        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        section = build_practice_section(self.practice)
        self.assertIn(self.incoming.email, section)
        self.assertNotIn(self.outgoing.email, section)

        sync_practice_reminders_for_season(self.season)
        reminder = PracticeReminderEmail.objects.get(
            anchor_practice=earlier,
            kind=PracticeReminderKind.AFTER_PRACTICE,
        )
        self.assertEqual(reminder.practice_one_id, self.practice.id)

        outgoing_recipient = ReminderRecipient(
            email=self.outgoing.email,
            first_name=self.outgoing.first_name,
            last_name=self.outgoing.last_name,
            kind=PracticeReminderRecipientKind.MENTOR,
            mentor_id=self.outgoing.id,
        )
        incoming_recipient = ReminderRecipient(
            email=self.incoming.email,
            first_name=self.incoming.first_name,
            last_name=self.incoming.last_name,
            kind=PracticeReminderRecipientKind.MENTOR,
            mentor_id=self.incoming.id,
        )
        self.assertEqual(mentor_schedule_notice(outgoing_recipient, self.practice), "")
        self.assertIn(
            "You are scheduled to mentor:",
            mentor_schedule_notice(incoming_recipient, self.practice),
        )

        _, outgoing_body = render_reminder_for_recipient(reminder, outgoing_recipient)
        _, incoming_body = render_reminder_for_recipient(reminder, incoming_recipient)
        self.assertNotIn("You are scheduled to mentor:", outgoing_body)
        self.assertIn("You are scheduled to mentor:", incoming_body)
        self.assertIn(self.incoming.email, incoming_body)
        self.assertNotIn(self.outgoing.email, incoming_body)

    def test_stale_attending_reply_after_swap_excluded_from_reminder(self):
        """Found-replacement wins over a leftover attending reply for reminders."""
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="Hello",
            recipient_season=self.season,
            task_completed_at=timezone.now(),
        )
        scheduled.practices.add(self.practice)
        token = ScheduledEmailMentorToken.objects.create(
            scheduled_email=scheduled,
            mentor=self.outgoing,
            included_in_send=True,
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token,
            mentor=self.outgoing,
            practice=self.practice,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace=self.outgoing.pace,
        )
        self.practice.sync_mentor_assignments_from_replies()

        self.practice.swap_assigned_mentor(self.outgoing, self.incoming)

        # Simulate incomplete cleanup: attending reply still present.
        ScheduledEmailMentorPracticeReply.objects.filter(
            mentor=self.outgoing,
            practice=self.practice,
        ).update(attendance=PracticeAttendanceReply.ATTENDING, pace=self.outgoing.pace)
        self.practice.sync_mentor_assignments_from_replies()

        roster_ids = {
            mentor.id
            for mentor, _pace, _reply, _assignment in self.practice.attending_mentor_roster_entries()
        }
        self.assertIn(self.incoming.id, roster_ids)
        self.assertNotIn(self.outgoing.id, roster_ids)

        section = build_practice_section(self.practice)
        self.assertIn(self.incoming.email, section)
        self.assertNotIn(self.outgoing.email, section)

        remote_out = Mentor.objects.create(
            first_name="Remote",
            last_name="Out",
            email="remote-out@example.com",
            cell_phone="555-0198",
            type=MentorTypes.REMOTE,
            pace=PaceTypes.NINE.value,
        )
        remote_in = Mentor.objects.create(
            first_name="Remote",
            last_name="In",
            email="remote-in@example.com",
            cell_phone="555-0199",
            type=MentorTypes.REMOTE,
            pace=PaceTypes.NINE.value,
        )
        remote_out.seasons.add(self.season)
        remote_in.seasons.add(self.season)
        other = Practice.objects.create(
            date=timezone.now() + timedelta(days=10),
            season=self.season,
            full_practice=True,
        )
        MentorPracticeAssignment.objects.create(
            mentor=remote_out,
            practice=other,
            pace=remote_out.pace,
            is_available=False,
        )
        other.mentors.add(remote_out)
        other.swap_assigned_mentor(remote_out, remote_in)

        sync_practice_reminders_for_season(self.season)
        reminder = PracticeReminderEmail.objects.get(practice_one=other)
        recipient_emails = {item.email for item in collect_recipients(reminder)}
        self.assertIn(remote_in.email, recipient_emails)
        self.assertNotIn(remote_out.email, recipient_emails)

    def test_swap_skips_all_emails_after_practice_has_started(self):
        coach = Coach.objects.create(
            first_name="Casey",
            last_name="Coach",
            email="casey@example.com",
        )
        coach.seasons.add(self.season)
        self.season.head_coach = coach
        self.season.save(update_fields=["head_coach"])

        self._mark_last_reminder_sent(self.practice)
        self.practice.date = timezone.now() - timedelta(minutes=5)
        self.practice.save(update_fields=["date", "updated_at"])

        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["mentor_confirmations"])
        self.assertIsNone(response.data["coach_notification"])
        self.assertEqual(len(mail.outbox), 0)
