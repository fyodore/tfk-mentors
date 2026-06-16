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
    MentorTypes,
    PaceTypes,
    Practice,
    PracticeAttendanceReply,
    PracticeReminderEmail,
    PracticeReminderKind,
    PracticeReminderSendRecord,
    ScheduledEmail,
    ScheduledEmailMentorPracticeReply,
    ScheduledEmailMentorToken,
    Season,
    TfkStaff,
)
from tfk_mentors.practice_reminder import (
    collect_recipients,
    default_subject,
    render_reminder_for_recipient,
    schedule_for_before_first_practice,
    send_practice_reminder,
    sync_practice_reminders_for_season,
    two_days_before_first_practice,
)


class PracticeReminderTests(TestCase):
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
                description=f"Plan for practice {offset}",
                start_location=f"Start {offset}",
                full_practice=True,
            )
            for offset in (1, 8, 15)
        ]

        self.staff = TfkStaff.objects.create(
            first_name="Sam",
            last_name="Staff",
            email="staff@example.com",
            cell_phone="555-0001",
        )
        self.coach = Coach.objects.create(
            first_name="Chris",
            last_name="Coach",
            email="coach@example.com",
            cell="555-0002",
        )
        self.coach.seasons.add(self.season)

        self.practice_mentor = Mentor.objects.create(
            first_name="Pat",
            last_name="Practice",
            email="practice@example.com",
            cell_phone="555-0003",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.ELEVEN.value,
        )
        self.practice_mentor.seasons.add(self.season)

        self.remote_mentor = Mentor.objects.create(
            first_name="Rem",
            last_name="Remote",
            email="remote@example.com",
            cell_phone="555-0004",
            type=MentorTypes.REMOTE,
            pace=PaceTypes.NINE.value,
        )
        self.remote_mentor.seasons.add(self.season)

        MentorPracticeAssignment.objects.create(
            mentor=self.practice_mentor,
            practice=self.practices[1],
            pace=PaceTypes.ELEVEN.value,
        )

        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=now,
            body_text="Hello",
            recipient_season=self.season,
        )
        scheduled.practices.set(self.practices)
        scheduled.sync_mentor_tokens()
        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=scheduled,
            mentor=self.remote_mentor,
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token,
            mentor=self.remote_mentor,
            practice=self.practices[1],
            attendance=PracticeAttendanceReply.ATTENDING,
            pace=PaceTypes.NINE.value,
        )

    def test_sync_creates_reminders_for_upcoming_practices(self):
        result = sync_practice_reminders_for_season(self.season)
        self.assertEqual(result["created"], 3)
        reminders = list(
            PracticeReminderEmail.objects.filter(season=self.season).order_by(
                "kind", "scheduled_send_at", "id"
            )
        )
        self.assertEqual(len(reminders), 3)
        before_first = PracticeReminderEmail.objects.get(
            anchor_practice=self.practices[0],
            kind=PracticeReminderKind.BEFORE_FIRST,
        )
        self.assertEqual(before_first.practice_one_id, self.practices[0].id)
        self.assertEqual(before_first.practice_two_id, self.practices[1].id)
        self.assertIsNone(before_first.scheduled_send_at)
        after_first = PracticeReminderEmail.objects.get(
            anchor_practice=self.practices[0],
            kind=PracticeReminderKind.AFTER_PRACTICE,
        )
        self.assertEqual(after_first.practice_one_id, self.practices[1].id)
        self.assertEqual(after_first.practice_two_id, self.practices[2].id)
        after_second = PracticeReminderEmail.objects.get(
            anchor_practice=self.practices[1],
            kind=PracticeReminderKind.AFTER_PRACTICE,
        )
        self.assertEqual(after_second.practice_one_id, self.practices[2].id)
        self.assertIsNone(after_second.practice_two_id)
        self.assertIn("TFK Practices", after_first.subject)
        self.assertIn("TFK Practice", after_second.subject)

    def test_before_first_within_48_hours_has_no_schedule(self):
        Practice.objects.all().delete()
        now = timezone.now()
        soon = Practice.objects.create(
            date=now + timedelta(hours=24),
            season=self.season,
            full_practice=True,
        )
        sync_practice_reminders_for_season(self.season)
        reminder = PracticeReminderEmail.objects.get(
            anchor_practice=soon,
            kind=PracticeReminderKind.BEFORE_FIRST,
        )
        self.assertIsNone(reminder.scheduled_send_at)
        self.assertIsNone(schedule_for_before_first_practice(soon.date))

    def test_before_first_scheduled_two_days_prior_at_615(self):
        Practice.objects.all().delete()
        now = timezone.now()
        later = Practice.objects.create(
            date=now + timedelta(days=10),
            season=self.season,
            full_practice=True,
        )
        expected = two_days_before_first_practice(later.date)
        sync_practice_reminders_for_season(self.season)
        reminder = PracticeReminderEmail.objects.get(
            anchor_practice=later,
            kind=PracticeReminderKind.BEFORE_FIRST,
        )
        self.assertEqual(reminder.scheduled_send_at, expected)

    def test_collect_recipients_includes_staff_coaches_and_mentors(self):
        sync_practice_reminders_for_season(self.season)
        reminder = PracticeReminderEmail.objects.get(
            anchor_practice=self.practices[0],
            kind=PracticeReminderKind.AFTER_PRACTICE,
        )
        recipients = collect_recipients(reminder)
        emails = {item.email for item in recipients}
        self.assertIn(self.staff.email, emails)
        self.assertIn(self.coach.email, emails)
        self.assertIn(self.practice_mentor.email, emails)
        self.assertIn(self.remote_mentor.email, emails)

    def test_render_includes_mentor_schedule_notice(self):
        sync_practice_reminders_for_season(self.season)
        reminder = PracticeReminderEmail.objects.get(
            anchor_practice=self.practices[0],
            kind=PracticeReminderKind.AFTER_PRACTICE,
        )
        recipients = collect_recipients(reminder)
        mentor_recipient = next(
            item for item in recipients if item.email == self.practice_mentor.email
        )
        subject, body = render_reminder_for_recipient(reminder, mentor_recipient)
        self.assertEqual(subject, default_subject(reminder.practice_one, reminder.practice_two))
        self.assertIn("You are scheduled to mentor:", body)
        self.assertIn("11-12", body)
        self.assertIn("Plan for practice 8", body)

    @patch("tfk_mentors.practice_reminder._verify_email_delivery")
    def test_send_creates_history_records(self, _mock_verify):
        sync_practice_reminders_for_season(self.season)
        reminder = PracticeReminderEmail.objects.get(
            anchor_practice=self.practices[0],
            kind=PracticeReminderKind.AFTER_PRACTICE,
        )
        result = send_practice_reminder(reminder)
        self.assertGreater(result["sent"], 0)
        reminder.refresh_from_db()
        self.assertIsNotNone(reminder.task_completed_at)
        self.assertEqual(
            reminder.recipients_emailed_count,
            PracticeReminderSendRecord.objects.filter(reminder=reminder).count(),
        )
        self.assertEqual(len(mail.outbox), reminder.recipients_emailed_count)

    def test_api_lists_and_patches_unsent_reminder(self):
        sync_practice_reminders_for_season(self.season)
        response = self.client.get(
            f"/api/practice-reminder-email/?season={self.season.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data), 1)
        reminder_id = response.data[0]["id"]
        new_time = timezone.now() + timedelta(days=30)
        patch_response = self.client.patch(
            f"/api/practice-reminder-email/{reminder_id}/",
            {
                "subject": "Custom subject",
                "body_text": "Dear {{first_name}},\n\nCustom body.",
                "scheduled_send_at": new_time.isoformat(),
            },
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.data["subject"], "Custom subject")

    @patch("tfk_mentors.practice_reminder._verify_email_delivery")
    def test_api_send_now_marks_complete(self, _mock_verify):
        sync_practice_reminders_for_season(self.season)
        reminder = PracticeReminderEmail.objects.filter(
            task_completed_at__isnull=True
        ).first()
        response = self.client.post(
            f"/api/practice-reminder-email/{reminder.id}/send-now/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        reminder.refresh_from_db()
        self.assertIsNotNone(reminder.task_completed_at)
        detail = self.client.get(f"/api/practice-reminder-email/{reminder.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertGreater(len(detail.data["send_records"]), 0)
