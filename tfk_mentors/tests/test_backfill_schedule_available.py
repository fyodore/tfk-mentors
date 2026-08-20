"""Coverage for the backfill_schedule_available management command."""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from tfk_mentors.models import (
    Mentor,
    MentorTypes,
    Practice,
    ScheduledEmail,
    ScheduledEmailMentorPracticeReply,
    ScheduledEmailMentorToken,
    Season,
)


class BackfillScheduleAvailableBaseTestCase(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2500)
        base = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
        # All three practices fall in the same calendar month so the mentor's
        # third selection overflows into "available" (2-per-month cap).
        month_start = base.replace(day=1) + timedelta(days=32)
        month_start = month_start.replace(day=1, hour=9)
        self.practice_one = Practice.objects.create(
            date=month_start + timedelta(days=1),
            season=self.season,
            mentor_selection_closed_at=timezone.now(),
        )
        self.practice_two = Practice.objects.create(
            date=month_start + timedelta(days=3),
            season=self.season,
            mentor_selection_closed_at=timezone.now(),
        )
        self.practice_three = Practice.objects.create(
            date=month_start + timedelta(days=5),
            season=self.season,
            mentor_selection_closed_at=timezone.now(),
        )
        self.mentor = Mentor.objects.create(
            first_name="Overflow",
            last_name="Backfill",
            email="overflowbackfill@example.com",
            cell_phone="555-0009",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        self.mentor.seasons.add(self.season)
        self.scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() - timedelta(days=1),
            body_text="Hello",
            recipient_season=self.season,
        )
        self.scheduled.practices.set(
            [self.practice_one, self.practice_two, self.practice_three]
        )
        self.scheduled.sync_mentor_tokens()
        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=self.scheduled, mentor=self.mentor
        )
        for practice in (self.practice_one, self.practice_two, self.practice_three):
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=token,
                mentor=self.mentor,
                practice=practice,
                attendance="attending",
                pace="9-10",
            )

    def _practice_ids(self):
        return [self.practice_one.id, self.practice_two.id, self.practice_three.id]


class BackfillScheduleAvailableNoMatchTests(TestCase):
    def test_no_matching_practices_prints_message_and_exits(self):
        out = StringIO()
        call_command(
            "backfill_schedule_available", "--season-id", "999999", stdout=out
        )
        self.assertIn("No matching practices.", out.getvalue())

    def test_missing_practice_id_raises_command_error(self):
        with self.assertRaises(CommandError):
            call_command(
                "backfill_schedule_available",
                "--practice-id",
                "999999",
                stdout=StringIO(),
            )


class BackfillScheduleAvailableAlreadyAvailableTests(
    BackfillScheduleAvailableBaseTestCase
):
    def test_skips_mentor_whose_newer_reply_already_marks_them_available(self):
        """compute_mentor_schedule surfaces the mentor as an overflow
        candidate for practice_three based on their older attending reply,
        but a newer available reply (from a second scheduled email) already
        covers them: the command should skip re-marking them."""
        older_reply = ScheduledEmailMentorPracticeReply.objects.get(
            mentor_token__scheduled_email=self.scheduled,
            mentor=self.mentor,
            practice=self.practice_three,
        )
        ScheduledEmailMentorPracticeReply.objects.filter(pk=older_reply.pk).update(
            updated_at=timezone.now() - timedelta(hours=2)
        )

        second_scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() - timedelta(hours=1),
            body_text="Follow up",
            recipient_season=self.season,
        )
        second_scheduled.practices.add(self.practice_three)
        second_scheduled.sync_mentor_tokens()
        second_token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=second_scheduled, mentor=self.mentor
        )
        newer_reply = ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=second_token,
            mentor=self.mentor,
            practice=self.practice_three,
            attendance="available",
            pace="9-10",
        )
        ScheduledEmailMentorPracticeReply.objects.filter(pk=newer_reply.pk).update(
            updated_at=timezone.now() - timedelta(hours=1)
        )

        out = StringIO()
        call_command(
            "backfill_schedule_available",
            *[f"--practice-id={pid}" for pid in self._practice_ids()],
            stdout=out,
        )
        self.assertIn(
            "No mentors need to be moved to available for the selected practices.",
            out.getvalue(),
        )


class BackfillScheduleAvailableDryRunTests(BackfillScheduleAvailableBaseTestCase):
    def test_dry_run_reports_moves_without_writing(self):
        out = StringIO()
        call_command(
            "backfill_schedule_available",
            "--dry-run",
            *[f"--practice-id={pid}" for pid in self._practice_ids()],
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("Would mark 1 mentor", output)
        self.assertIn("Dry run only", output)
        self.practice_three.refresh_from_db()
        self.assertEqual(
            list(self.practice_three.latest_available_mentor_replies()), []
        )


class BackfillScheduleAvailableFilterFlagsTests(BackfillScheduleAvailableBaseTestCase):
    def test_include_open_and_upcoming_only_flags_are_applied(self):
        # Reopen the practices so the default (selection-closed-only) filter
        # would normally exclude them; --include-open bypasses that, and
        # --upcoming-only further restricts to future practices (all three
        # are in the future here, so nothing should be filtered out).
        Practice.objects.filter(
            pk__in=self._practice_ids()
        ).update(mentor_selection_closed_at=None)

        out = StringIO()
        call_command(
            "backfill_schedule_available",
            "--include-open",
            "--upcoming-only",
            "--season-id",
            str(self.season.id),
            stdout=out,
        )
        self.assertIn("Marked 1 mentor selection(s) as available.", out.getvalue())


class BackfillScheduleAvailableApplyTests(BackfillScheduleAvailableBaseTestCase):
    def test_marks_overflowing_mentor_available(self):
        out = StringIO()
        call_command(
            "backfill_schedule_available",
            *[f"--practice-id={pid}" for pid in self._practice_ids()],
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("Marked 1 mentor selection(s) as available.", output)
        available_ids = {
            reply.mentor_id
            for reply in self.practice_three.latest_available_mentor_replies()
        }
        self.assertIn(self.mentor.id, available_ids)

    def test_second_run_reports_nothing_left_to_move(self):
        call_command(
            "backfill_schedule_available",
            *[f"--practice-id={pid}" for pid in self._practice_ids()],
            stdout=StringIO(),
        )
        out = StringIO()
        call_command(
            "backfill_schedule_available",
            *[f"--practice-id={pid}" for pid in self._practice_ids()],
            stdout=out,
        )
        self.assertIn(
            "No mentors need to be moved to available for the selected practices.",
            out.getvalue(),
        )


class BackfillScheduleAvailableErrorHandlingTests(BackfillScheduleAvailableBaseTestCase):
    def test_mentor_not_found_is_recorded_and_raises_command_error(self):
        fake_schedule = {
            "practices": [
                {
                    "practice_id": self.practice_three.id,
                    "available_by_pace": {
                        "9-10": [
                            {
                                "mentor_id": 9999999,
                                "pace": "9-10",
                                "first_name": "Ghost",
                                "last_name": "Mentor",
                            }
                        ]
                    },
                }
            ]
        }
        with patch(
            "tfk_mentors.management.commands.backfill_schedule_available.compute_mentor_schedule",
            return_value=fake_schedule,
        ):
            out = StringIO()
            with self.assertRaises(CommandError):
                call_command(
                    "backfill_schedule_available",
                    *[f"--practice-id={pid}" for pid in self._practice_ids()],
                    stdout=out,
                )
            self.assertIn("Mentor not found.", out.getvalue())

    def test_mark_mentor_available_exception_is_recorded_and_raises_command_error(
        self,
    ):
        with patch(
            "tfk_mentors.models.Practice.mark_mentor_available",
            side_effect=RuntimeError("boom"),
        ):
            out = StringIO()
            with self.assertRaises(CommandError):
                call_command(
                    "backfill_schedule_available",
                    *[f"--practice-id={pid}" for pid in self._practice_ids()],
                    stdout=out,
                )
            self.assertIn("boom", out.getvalue())
