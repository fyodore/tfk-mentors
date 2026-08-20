"""Coverage for mentor_scheduling.py branches not exercised by the main
scheduling test suite (malformed payloads, defensive edge cases)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.mentor_scheduling import (
    _assignment_attendance,
    _latest_attending_replies_for_practices,
    apply_mentor_schedule,
    compute_mentor_schedule,
    normalize_and_validate_schedule_payload,
    schedule_assignment_fingerprint,
    validate_schedule_payload,
)
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


class LatestAttendingRepliesTests(TestCase):
    def test_returns_empty_list_for_no_practice_ids(self):
        self.assertEqual(_latest_attending_replies_for_practices([]), [])


class ComputeMentorScheduleEdgeCaseTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2100)

    def _scheduled_for(self, practices):
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_season=self.season,
        )
        scheduled.practices.set(practices)
        scheduled.sync_mentor_tokens()
        return scheduled

    def test_skips_replies_with_no_resolvable_pace(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=5), season=self.season
        )
        mentor = Mentor.objects.create(
            first_name="No",
            last_name="Pace",
            email="nopace_sched@example.com",
            cell_phone="555-0001",
            type=MentorTypes.PRACTICE,
            pace="",
        )
        mentor.seasons.add(self.season)
        scheduled = self._scheduled_for([practice])
        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=scheduled, mentor=mentor
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token,
            mentor=mentor,
            practice=practice,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="",
        )
        result = compute_mentor_schedule([practice])
        self.assertEqual(result["summary"]["assignment_rows"], 0)
        self.assertEqual(result["summary"]["available_rows"], 0)
        self.assertEqual(result["remote_mentors"], [])

    def test_remote_mentor_with_multiple_practices_reuses_entry(self):
        practice_one = Practice.objects.create(
            date=timezone.now() + timedelta(days=5), season=self.season
        )
        practice_two = Practice.objects.create(
            date=timezone.now() + timedelta(days=12), season=self.season
        )
        remote = Mentor.objects.create(
            first_name="Remote",
            last_name="Two",
            email="remotetwo@example.com",
            type=MentorTypes.REMOTE,
            pace="9-10",
        )
        remote.seasons.add(self.season)
        scheduled = self._scheduled_for([practice_one, practice_two])
        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=scheduled, mentor=remote
        )
        for practice in (practice_one, practice_two):
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=token,
                mentor=remote,
                practice=practice,
                attendance=PracticeAttendanceReply.ATTENDING,
                pace="9-10",
            )
        result = compute_mentor_schedule([practice_one, practice_two])
        self.assertEqual(len(result["remote_mentors"]), 1)
        self.assertEqual(len(result["remote_mentors"][0]["practices"]), 2)

    def test_ignores_selections_from_mentor_with_unrecognized_type(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=5), season=self.season
        )
        mentor = Mentor.objects.create(
            first_name="Odd",
            last_name="Type",
            email="oddtype@example.com",
            cell_phone="555-0002",
            type="Something Else",
            pace="9-10",
        )
        mentor.seasons.add(self.season)
        scheduled = self._scheduled_for([practice])
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
        result = compute_mentor_schedule([practice])
        self.assertEqual(result["summary"]["assignment_rows"], 0)
        self.assertEqual(result["remote_mentors"], [])

    def test_duplicate_reply_across_scheduled_emails_uses_latest(self):
        """Two attending replies for the same (mentor, practice) from different
        scheduled emails: only the most recently updated one is used."""
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=5), season=self.season
        )
        mentor = Mentor.objects.create(
            first_name="Dup",
            last_name="Reply",
            email="dupreply@example.com",
            cell_phone="555-0003",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        mentor.seasons.add(self.season)

        older_email = self._scheduled_for([practice])
        older_token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=older_email, mentor=mentor
        )
        older_reply = ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=older_token,
            mentor=mentor,
            practice=practice,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="8-9",
        )
        ScheduledEmailMentorPracticeReply.objects.filter(pk=older_reply.pk).update(
            updated_at=timezone.now() - timedelta(hours=2)
        )

        newer_email = self._scheduled_for([practice])
        newer_token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=newer_email, mentor=mentor
        )
        newer_reply = ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=newer_token,
            mentor=mentor,
            practice=practice,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="10-11",
        )
        ScheduledEmailMentorPracticeReply.objects.filter(pk=newer_reply.pk).update(
            updated_at=timezone.now() - timedelta(hours=1)
        )

        result = compute_mentor_schedule([practice])
        assigned_rows = [
            row
            for rows in result["practices"][0]["assignments_by_pace"].values()
            for row in rows
        ]
        self.assertEqual(len(assigned_rows), 1)
        self.assertEqual(assigned_rows[0]["pace"], "10-11")


class AssignmentAttendanceTests(TestCase):
    def test_falls_back_to_attending_for_non_attending_value(self):
        self.assertEqual(
            _assignment_attendance({"attendance": PracticeAttendanceReply.AVAILABLE}),
            PracticeAttendanceReply.ATTENDING,
        )

    def test_missing_attendance_defaults_to_attending(self):
        self.assertEqual(_assignment_attendance({}), PracticeAttendanceReply.ATTENDING)

    def test_preserves_first_half(self):
        self.assertEqual(
            _assignment_attendance({"attendance": PracticeAttendanceReply.FIRST_HALF}),
            PracticeAttendanceReply.FIRST_HALF,
        )


class ApplyScheduleRowWithoutScheduledEmailTests(TestCase):
    """When a practice has no linked ScheduledEmail, apply falls back to
    direct MentorPracticeAssignment rows instead of email-reply rows."""

    def setUp(self):
        self.season = Season.objects.create(year=2101)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=5), season=self.season
        )
        self.mentor = Mentor.objects.create(
            first_name="Direct",
            last_name="Assign",
            email="directassign_sched@example.com",
            cell_phone="555-0004",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        self.mentor.seasons.add(self.season)

    def test_applies_attending_assignment_without_scheduled_email(self):
        schedule = {
            "practices": [
                {
                    "practice_id": self.practice.id,
                    "assignments_by_pace": {
                        "9-10": [{"mentor_id": self.mentor.id, "pace": "9-10"}]
                    },
                    "available_by_pace": {},
                }
            ]
        }
        applied = apply_mentor_schedule([self.practice], schedule)
        self.assertEqual(applied["assigned"], 1)
        self.assertEqual(applied["errors"], [])
        self.assertIn(self.mentor.id, self.practice.assigned_mentor_ids())

    def test_applies_available_assignment_without_scheduled_email(self):
        schedule = {
            "practices": [
                {
                    "practice_id": self.practice.id,
                    "assignments_by_pace": {},
                    "available_by_pace": {
                        "9-10": [{"mentor_id": self.mentor.id, "pace": "9-10"}]
                    },
                }
            ]
        }
        applied = apply_mentor_schedule([self.practice], schedule)
        self.assertEqual(applied["available"], 1)
        self.assertEqual(applied["errors"], [])
        self.assertNotIn(self.mentor.id, self.practice.assigned_mentor_ids())
        self.assertIn(self.mentor.id, self.practice.mentor_ids_on_practice())


class ApplyMentorScheduleMalformedRowTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2102)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=5), season=self.season
        )
        self.mentor = Mentor.objects.create(
            first_name="Err",
            last_name="Available",
            email="erravailable@example.com",
            cell_phone="555-0005",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        self.mentor.seasons.add(self.season)

    def test_non_integer_practice_id_is_skipped(self):
        schedule = {"practices": [{"practice_id": "not-an-int"}]}
        applied = apply_mentor_schedule([self.practice], schedule)
        self.assertEqual(applied["assigned"], 0)
        self.assertEqual(applied["available"], 0)
        self.assertEqual(applied["errors"], [])

    def test_practice_id_not_in_provided_practices_is_skipped(self):
        schedule = {
            "practices": [
                {
                    "practice_id": self.practice.id + 999,
                    "assignments_by_pace": {},
                    "available_by_pace": {},
                }
            ]
        }
        applied = apply_mentor_schedule([self.practice], schedule)
        self.assertEqual(applied["assigned"], 0)
        self.assertEqual(applied["available"], 0)
        self.assertEqual(applied["errors"], [])

    def test_available_row_error_is_recorded_and_practice_not_closed(self):
        schedule = {
            "practices": [
                {
                    "practice_id": self.practice.id,
                    "assignments_by_pace": {},
                    "available_by_pace": {
                        "not-a-pace": [
                            {"mentor_id": self.mentor.id, "pace": "not-a-pace"}
                        ]
                    },
                }
            ]
        }
        applied = apply_mentor_schedule([self.practice], schedule)
        self.assertEqual(applied["available"], 0)
        self.assertEqual(len(applied["errors"]), 1)
        self.assertEqual(applied["errors"][0]["action"], "available")
        self.assertEqual(applied["closed_practice_ids"], [])


class ScheduleValidationEdgeCaseTests(TestCase):
    def setUp(self):
        self.practice_ids = [1, 2]

    def test_rejects_non_dict_schedule(self):
        error = validate_schedule_payload("not-a-dict", self.practice_ids)
        self.assertEqual(error, "schedule must be an object.")

    def test_rejects_non_list_practices(self):
        error = validate_schedule_payload(
            {"practices": "not-a-list"}, self.practice_ids
        )
        self.assertEqual(error, "schedule.practices must be a list.")

    def test_rejects_non_dict_practice_row(self):
        error = validate_schedule_payload(
            {"practices": ["not-a-dict"]}, self.practice_ids
        )
        self.assertEqual(error, "schedule.practices entries must be objects.")

    def test_rejects_non_integer_practice_id(self):
        error = validate_schedule_payload(
            {"practices": [{"practice_id": "abc"}]}, self.practice_ids
        )
        self.assertEqual(
            error, "schedule.practices entries require integer practice_id."
        )

    def test_rejects_practice_id_not_requested(self):
        error = validate_schedule_payload(
            {"practices": [{"practice_id": 999}]}, self.practice_ids
        )
        self.assertIn("was not requested", error)

    def test_rejects_duplicate_practice_id(self):
        error = validate_schedule_payload(
            {
                "practices": [
                    {"practice_id": 1, "assignments_by_pace": {}, "available_by_pace": {}},
                    {"practice_id": 1, "assignments_by_pace": {}, "available_by_pace": {}},
                ]
            },
            self.practice_ids,
        )
        self.assertIn("more than once", error)

    def test_rejects_non_dict_assignments_by_pace(self):
        error = validate_schedule_payload(
            {
                "practices": [
                    {
                        "practice_id": 1,
                        "assignments_by_pace": ["not", "a", "dict"],
                        "available_by_pace": {},
                    }
                ]
            },
            self.practice_ids,
        )
        self.assertIn("assignments_by_pace object", error)

    def test_rejects_non_dict_mentor_row_in_pace_list(self):
        error = validate_schedule_payload(
            {
                "practices": [
                    {
                        "practice_id": 1,
                        "assignments_by_pace": {"9-10": ["not-a-dict"]},
                        "available_by_pace": {},
                    }
                ]
            },
            self.practice_ids,
        )
        self.assertIn("must be an object", error)

    def test_rejects_non_integer_mentor_id(self):
        error = validate_schedule_payload(
            {
                "practices": [
                    {
                        "practice_id": 1,
                        "assignments_by_pace": {"9-10": [{"mentor_id": "abc"}]},
                        "available_by_pace": {},
                    }
                ]
            },
            self.practice_ids,
        )
        self.assertIn("requires integer mentor_id", error)

    def test_rejects_invalid_available_by_pace_after_valid_assignments(self):
        error = validate_schedule_payload(
            {
                "practices": [
                    {
                        "practice_id": 1,
                        "assignments_by_pace": {"9-10": [{"mentor_id": 5}]},
                        "available_by_pace": ["not", "a", "dict"],
                    }
                ]
            },
            self.practice_ids,
        )
        self.assertIn("available_by_pace object", error)

    def test_rejects_missing_practice_id(self):
        error = validate_schedule_payload(
            {
                "practices": [
                    {
                        "practice_id": 1,
                        "assignments_by_pace": {},
                        "available_by_pace": {},
                    }
                ]
            },
            self.practice_ids,
        )
        self.assertIn("missing practice_id 2", error)

    def test_valid_schedule_normalizes_and_returns_no_error(self):
        error, normalized = normalize_and_validate_schedule_payload(
            {
                "practices": [
                    {
                        "practice_id": "1",
                        "assignments_by_pace": {"9-10": [{"mentor_id": "5"}]},
                        "available_by_pace": {},
                    },
                    {
                        "practice_id": 2,
                        "assignments_by_pace": {},
                        "available_by_pace": {},
                    },
                ]
            },
            self.practice_ids,
        )
        self.assertIsNone(error)
        self.assertEqual(normalized["practices"][0]["practice_id"], 1)
        self.assertEqual(
            normalized["practices"][0]["assignments_by_pace"]["9-10"][0]["mentor_id"],
            5,
        )


class ScheduleAssignmentFingerprintEdgeCaseTests(TestCase):
    def test_skips_malformed_rows_and_includes_only_valid_ones(self):
        schedule = {
            "practices": [
                {"practice_id": "not-an-int"},
                {
                    "practice_id": 1,
                    "assignments_by_pace": {
                        "9-10": "not-a-list",
                        "10-11": [
                            "not-a-dict",
                            {"mentor_id": "bad"},
                            {"mentor_id": 5, "pace": "10-11"},
                        ],
                    },
                    "available_by_pace": {
                        "8-9": "not-a-list",
                        "9-10": [
                            "not-a-dict",
                            {"mentor_id": "bad"},
                            {"mentor_id": 7, "pace": "9-10"},
                        ],
                    },
                },
            ]
        }
        fingerprint = schedule_assignment_fingerprint(schedule)
        self.assertEqual(
            fingerprint,
            {
                (1, 5, "10-11", "assign"),
                (1, 7, "9-10", "available"),
            },
        )


class ScheduleApplyAvailableFingerprintApiTests(TestCase):
    """Exercise the full preview->apply flow when the preview includes
    available-by-pace rows (overflow mentors), through the real API."""

    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

        self.season = Season.objects.create(year=2103)
        base = timezone.now() + timedelta(days=14)
        self.practice_one = Practice.objects.create(
            date=base.replace(day=5, hour=9, minute=0, second=0, microsecond=0),
            season=self.season,
        )
        self.practice_two = Practice.objects.create(
            date=base.replace(day=12, hour=9, minute=0, second=0, microsecond=0),
            season=self.season,
        )
        self.practice_three = Practice.objects.create(
            date=base.replace(day=19, hour=9, minute=0, second=0, microsecond=0),
            season=self.season,
        )
        self.scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() - timedelta(days=1),
            body_text="Hello",
            recipient_season=self.season,
        )
        self.scheduled.practices.set(
            [self.practice_one, self.practice_two, self.practice_three]
        )

        self.mentor = Mentor.objects.create(
            first_name="Overflow",
            last_name="Mentor",
            email="overflowmentor@example.com",
            cell_phone="555-0006",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        self.mentor.seasons.add(self.season)
        self.scheduled.sync_mentor_tokens()
        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=self.scheduled, mentor=self.mentor
        )
        for practice in (self.practice_one, self.practice_two, self.practice_three):
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=token,
                mentor=self.mentor,
                practice=practice,
                attendance=PracticeAttendanceReply.ATTENDING,
                pace="9-10",
            )

    def test_apply_with_available_overflow_rows_via_api(self):
        practice_ids = [
            self.practice_one.id,
            self.practice_two.id,
            self.practice_three.id,
        ]
        preview = self.client.post(
            "/api/practices/schedule-mentors/",
            {"practice_ids": practice_ids},
            format="json",
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["summary"]["available_rows"], 1)

        apply_response = self.client.post(
            "/api/practices/schedule-mentors/",
            {
                "practice_ids": practice_ids,
                "apply": True,
                "schedule": preview.data,
            },
            format="json",
        )
        self.assertEqual(apply_response.status_code, 200)
        self.assertEqual(apply_response.data["applied"]["available"], 1)
        self.assertEqual(apply_response.data["applied"]["errors"], [])
