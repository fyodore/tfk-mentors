"""Coverage for practice_reminder.py branches not exercised by the main
reminder test suite (naive datetimes, blank emails, defensive edge cases)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import (
    Coach,
    CoachPracticeAssignment,
    Mentor,
    MentorPracticeAssignment,
    MentorTypes,
    Practice,
    PracticeAttendanceReply,
    PracticeReminderEmail,
    PracticeReminderKind,
    ScheduledEmail,
    ScheduledEmailMentorPracticeReply,
    ScheduledEmailMentorToken,
    Season,
    TfkStaff,
)
from tfk_mentors.practice_reminder import (
    _season_base_recipient_emails,
    build_practice_section,
    collect_recipients,
    format_practice_date,
    morning_after_practice,
    recipient_counts_for_reminders,
    schedule_for_before_first_practice,
    send_practice_reminder,
    sync_practice_reminders_for_season,
    two_days_before_first_practice,
)


class NaiveDatetimeHandlingTests(TestCase):
    """Each helper localizes naive datetimes before formatting/computing offsets."""

    def setUp(self):
        self.naive = datetime(2026, 3, 5, 9, 0)

    def test_format_practice_date_localizes_naive_datetime(self):
        fake_practice = SimpleNamespace(date=self.naive)
        result = format_practice_date(fake_practice)
        self.assertIn("2026", result)

    def test_morning_after_practice_localizes_naive_datetime(self):
        result = morning_after_practice(self.naive)
        self.assertEqual(result.tzinfo is not None, True)

    def test_two_days_before_first_practice_localizes_naive_datetime(self):
        result = two_days_before_first_practice(self.naive)
        self.assertEqual(result.tzinfo is not None, True)

    def test_schedule_for_before_first_practice_localizes_naive_datetime(self):
        far_future_naive = datetime.now().replace(microsecond=0) + timedelta(days=30)
        result = schedule_for_before_first_practice(far_future_naive)
        self.assertIsNotNone(result)


class BuildPracticeSectionEdgeCaseTests(TestCase):
    def test_returns_empty_string_for_none_practice(self):
        self.assertEqual(build_practice_section(None), "")

    def test_includes_coach_contact_line_when_assigned(self):
        season = Season.objects.create(year=2300)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=season
        )
        coach = Coach.objects.create(
            first_name="Casey",
            last_name="Coach",
            email="caseycoach@example.com",
            cell="555-0100",
        )
        coach.seasons.add(season)
        CoachPracticeAssignment.objects.create(coach=coach, practice=practice)

        section = build_practice_section(practice)
        self.assertIn("Casey Coach: caseycoach@example.com", section)
        self.assertIn("555-0100", section)

    def test_skips_mentor_already_counted_as_available(self):
        """A mentor attending via reply but with a stale is_available
        assignment row is excluded from the by-pace mentor listing."""
        season = Season.objects.create(year=2301)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=season
        )
        mentor = Mentor.objects.create(
            first_name="Stale",
            last_name="Available",
            email="staleavailable@example.com",
            cell_phone="555-0101",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        mentor.seasons.add(season)
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_season=season,
        )
        scheduled.practices.add(practice)
        scheduled.sync_mentor_tokens()
        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=scheduled, mentor=mentor
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token,
            mentor=mentor,
            practice=practice,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="9-10",
        )
        MentorPracticeAssignment.objects.create(
            mentor=mentor, practice=practice, pace="9-10", is_available=True
        )

        section = build_practice_section(practice)
        self.assertNotIn("Stale Available", section)


class CollectRecipientsBlankEmailTests(TestCase):
    def test_ignores_recipients_with_blank_email(self):
        season = Season.objects.create(year=2302)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=season
        )
        no_email_coach = Coach.objects.create(
            first_name="No", last_name="Email", email=""
        )
        no_email_coach.seasons.add(season)
        reminder = PracticeReminderEmail.objects.create(
            season=season,
            kind=PracticeReminderKind.BEFORE_FIRST,
            anchor_practice=practice,
            practice_one=practice,
            subject="Subject",
            body_text="Body",
        )
        recipients = collect_recipients(reminder)
        self.assertEqual(recipients, [])


class SeasonBaseRecipientEmailsBlankTests(TestCase):
    def test_whitespace_only_email_is_normalized_away(self):
        season = Season.objects.create(year=2303)
        coach = Coach.objects.create(first_name="Blank", last_name="Email", email=" ")
        coach.seasons.add(season)
        emails = _season_base_recipient_emails(season)
        self.assertEqual(emails, set())


class RecipientCountsForRemindersEdgeCaseTests(TestCase):
    def test_sent_reminder_uses_recorded_recipient_count(self):
        season = Season.objects.create(year=2304)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=season
        )
        sent = PracticeReminderEmail.objects.create(
            season=season,
            kind=PracticeReminderKind.BEFORE_FIRST,
            anchor_practice=practice,
            practice_one=practice,
            subject="Subject",
            body_text="Body",
            task_completed_at=timezone.now(),
            recipients_emailed_count=9,
        )
        counts = recipient_counts_for_reminders([sent])
        self.assertEqual(counts[sent.pk], 9)

    def test_remote_mentor_blank_email_excluded_from_unsent_count(self):
        season = Season.objects.create(year=2305)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=season
        )
        remote = Mentor.objects.create(
            first_name="Blank",
            last_name="Remote",
            email=" ",
            type=MentorTypes.REMOTE,
            pace="9-10",
        )
        remote.seasons.add(season)
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_season=season,
        )
        scheduled.practices.add(practice)
        scheduled.sync_mentor_tokens()
        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=scheduled, mentor=remote
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token,
            mentor=remote,
            practice=practice,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="9-10",
        )
        unsent = PracticeReminderEmail.objects.create(
            season=season,
            kind=PracticeReminderKind.BEFORE_FIRST,
            anchor_practice=practice,
            practice_one=practice,
            subject="Subject",
            body_text="Body",
        )
        counts = recipient_counts_for_reminders([unsent])
        self.assertEqual(counts[unsent.pk], 0)

    def test_api_list_includes_sent_reminder_recipient_count(self):
        client = APIClient()
        session = client.session
        session["site_authenticated"] = True
        session.save()

        season = Season.objects.create(year=2306)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=season
        )
        sent = PracticeReminderEmail.objects.create(
            season=season,
            kind=PracticeReminderKind.BEFORE_FIRST,
            anchor_practice=practice,
            practice_one=practice,
            subject="Subject",
            body_text="Body",
            task_completed_at=timezone.now(),
            recipients_emailed_count=4,
        )
        response = client.get(f"/api/practice-reminder-email/?season={season.id}")
        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.data if item["id"] == sent.id)
        self.assertEqual(row["recipient_count"], 4)


class SyncPracticeRemindersEdgeCaseTests(TestCase):
    def test_no_practices_deletes_before_first_reminder(self):
        season = Season.objects.create(year=2307)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=season
        )
        sync_practice_reminders_for_season(season)
        self.assertTrue(
            PracticeReminderEmail.objects.filter(
                season=season, kind=PracticeReminderKind.BEFORE_FIRST
            ).exists()
        )

        practice.delete()
        result = sync_practice_reminders_for_season(season)
        self.assertEqual(result["created"], 0)
        self.assertFalse(
            PracticeReminderEmail.objects.filter(
                season=season, kind=PracticeReminderKind.BEFORE_FIRST
            ).exists()
        )

    def test_resync_skips_already_sent_reminder(self):
        season = Season.objects.create(year=2308)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=10), season=season
        )
        sync_practice_reminders_for_season(season)
        reminder = PracticeReminderEmail.objects.get(
            season=season, kind=PracticeReminderKind.BEFORE_FIRST
        )
        reminder.task_completed_at = timezone.now()
        reminder.subject = "Frozen subject"
        reminder.save(update_fields=["task_completed_at", "subject"])

        result = sync_practice_reminders_for_season(season)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 0)
        reminder.refresh_from_db()
        self.assertEqual(reminder.subject, "Frozen subject")

    def test_resync_fills_in_schedule_once_far_enough_out(self):
        season = Season.objects.create(year=2309)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=10), season=season
        )
        sync_practice_reminders_for_season(season)
        reminder = PracticeReminderEmail.objects.get(
            season=season, kind=PracticeReminderKind.BEFORE_FIRST
        )
        self.assertIsNotNone(reminder.scheduled_send_at)

        # Simulate an earlier sync that ran while the practice was <48h away.
        PracticeReminderEmail.objects.filter(pk=reminder.pk).update(
            scheduled_send_at=None
        )
        reminder.refresh_from_db()
        self.assertIsNone(reminder.scheduled_send_at)

        result = sync_practice_reminders_for_season(season)
        self.assertEqual(result["updated"], 1)
        reminder.refresh_from_db()
        self.assertIsNotNone(reminder.scheduled_send_at)


class SendPracticeReminderEdgeCaseTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2310)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=self.season
        )

    def test_raises_when_already_sent(self):
        reminder = PracticeReminderEmail.objects.create(
            season=self.season,
            kind=PracticeReminderKind.BEFORE_FIRST,
            anchor_practice=self.practice,
            practice_one=self.practice,
            subject="Subject",
            body_text="Body",
            task_completed_at=timezone.now(),
        )
        with self.assertRaises(ValueError):
            send_practice_reminder(reminder)

    def test_raises_when_no_recipients(self):
        reminder = PracticeReminderEmail.objects.create(
            season=self.season,
            kind=PracticeReminderKind.BEFORE_FIRST,
            anchor_practice=self.practice,
            practice_one=self.practice,
            subject="Subject",
            body_text="Body",
        )
        with self.assertRaises(ValueError):
            send_practice_reminder(reminder)

    def test_dry_run_returns_sample_without_sending(self):
        staff = TfkStaff.objects.create(
            first_name="Sam", last_name="Staff", email="samstaffdry@example.com"
        )
        reminder = PracticeReminderEmail.objects.create(
            season=self.season,
            kind=PracticeReminderKind.BEFORE_FIRST,
            anchor_practice=self.practice,
            practice_one=self.practice,
            subject="Subject",
            body_text="Dear {{first_name}}, see you soon.",
        )
        result = send_practice_reminder(reminder, dry_run=True)
        self.assertEqual(result["recipients"], 1)
        self.assertIn("Dear Sam", result["sample_body"])
        reminder.refresh_from_db()
        self.assertIsNone(reminder.task_completed_at)
