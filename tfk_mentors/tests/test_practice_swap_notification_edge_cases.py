"""Coverage for practice_swap_notification.py branches not exercised by the
main mentor-swap feature tests (naive datetimes, blank emails, dry runs)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from tfk_mentors.models import Coach, Mentor, MentorTypes, Practice, Season
from tfk_mentors.practice_swap_notification import (
    coaches_for_swap_notification,
    practice_has_started,
    send_mentor_swap_coach_notification,
    send_mentor_swap_confirmations,
)


class PracticeHasStartedNaiveDatetimeTests(TestCase):
    def test_localizes_naive_datetime_before_comparing(self):
        past_naive = datetime.now() - timedelta(days=1)
        future_naive = datetime.now() + timedelta(days=1)
        self.assertTrue(practice_has_started(SimpleNamespace(date=past_naive)))
        self.assertFalse(practice_has_started(SimpleNamespace(date=future_naive)))


class CoachesForSwapNotificationBlankEmailTests(TestCase):
    def test_skips_coach_with_blank_email(self):
        season = Season.objects.create(year=2400)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=season
        )
        blank_email_coach = Coach.objects.create(
            first_name="Blank", last_name="Email", email=""
        )
        blank_email_coach.seasons.add(season)
        good_coach = Coach.objects.create(
            first_name="Good", last_name="Coach", email="goodcoach@example.com"
        )
        good_coach.seasons.add(season)

        coaches = coaches_for_swap_notification(practice)
        self.assertNotIn(blank_email_coach, coaches)
        self.assertIn(good_coach, coaches)


class SendMentorSwapConfirmationsDryRunTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2401)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=self.season
        )
        self.outgoing = Mentor.objects.create(
            first_name="Out",
            last_name="Going",
            email="outgoingswap@example.com",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        self.incoming = Mentor.objects.create(
            first_name="In",
            last_name="Coming",
            email="incomingswap@example.com",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )

    def test_dry_run_with_recipients_does_not_send(self):
        result = send_mentor_swap_confirmations(
            self.practice, self.outgoing, self.incoming, dry_run=True
        )
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["recipients"], 2)
        self.assertFalse(result["skipped"])


class SendMentorSwapCoachNotificationDryRunTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2402)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=self.season
        )
        self.coach = Coach.objects.create(
            first_name="Notify", last_name="Coach", email="notifycoach@example.com"
        )
        self.coach.seasons.add(self.season)
        self.outgoing = Mentor.objects.create(
            first_name="Out",
            last_name="Going",
            email="outgoingcoachnotify@example.com",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        self.incoming = Mentor.objects.create(
            first_name="In",
            last_name="Coming",
            email="incomingcoachnotify@example.com",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )

    def test_dry_run_with_recipients_does_not_send(self):
        result = send_mentor_swap_coach_notification(
            self.practice, self.outgoing, self.incoming, "9-10", dry_run=True
        )
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["recipients"], 1)
        self.assertFalse(result["skipped"])
