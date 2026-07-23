from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.mentor_scheduling import compute_mentor_schedule
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


class MentorSchedulingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

        self.season = Season.objects.create(year=2026)
        base = timezone.now() + timedelta(days=14)
        self.practice_one = Practice.objects.create(
            date=base.replace(day=5, hour=9, minute=0, second=0, microsecond=0),
            season=self.season,
            full_practice=True,
        )
        self.practice_two = Practice.objects.create(
            date=base.replace(day=12, hour=9, minute=0, second=0, microsecond=0),
            season=self.season,
            full_practice=True,
        )
        self.practice_three = Practice.objects.create(
            date=base.replace(day=19, hour=9, minute=0, second=0, microsecond=0),
            season=self.season,
            full_practice=True,
        )

        self.scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() - timedelta(days=1),
            body_text="Hello",
            recipient_season=self.season,
        )
        self.scheduled.practices.set(
            [self.practice_one, self.practice_two, self.practice_three]
        )

    def _create_practice_mentor(self, *, first_name, last_name, email, pace, selections):
        mentor = Mentor.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=email,
            cell_phone="555-0100",
            type=MentorTypes.PRACTICE,
            pace=pace,
        )
        mentor.seasons.add(self.season)
        self.scheduled.sync_mentor_tokens()
        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=self.scheduled,
            mentor=mentor,
        )
        for practice in selections:
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=token,
                mentor=mentor,
                practice=practice,
                attendance=PracticeAttendanceReply.ATTENDING,
                pace=pace,
            )
        return mentor

    def test_prioritizes_mentors_with_fewer_selections(self):
        many = self._create_practice_mentor(
            first_name="Many",
            last_name="Choices",
            email="many@example.com",
            pace="9-10",
            selections=[self.practice_one, self.practice_two, self.practice_three],
        )
        few = self._create_practice_mentor(
            first_name="Few",
            last_name="Choices",
            email="few@example.com",
            pace="9-10",
            selections=[self.practice_one],
        )
        practices = [self.practice_one, self.practice_two, self.practice_three]
        result = compute_mentor_schedule(practices)
        assigned_ids = {
            row["mentor_id"]
            for practice_row in result["practices"]
            for rows in practice_row["assignments_by_pace"].values()
            for row in rows
        }
        self.assertIn(few.id, assigned_ids)
        self.assertIn(many.id, assigned_ids)
        practice_one_rows = next(
            row
            for row in result["practices"]
            if row["practice_id"] == self.practice_one.id
        )
        pace_rows = practice_one_rows["assignments_by_pace"]["9-10"]
        self.assertEqual(pace_rows[0]["last_name"], "Choices")
        self.assertEqual(pace_rows[0]["selection_count"], 1)

    def test_limits_two_practices_per_month(self):
        mentor = self._create_practice_mentor(
            first_name="Busy",
            last_name="Runner",
            email="busy@example.com",
            pace="10-11",
            selections=[self.practice_one, self.practice_two, self.practice_three],
        )
        result = compute_mentor_schedule(
            [self.practice_one, self.practice_two, self.practice_three]
        )
        assigned = [
            practice_row["practice_id"]
            for practice_row in result["practices"]
            for rows in practice_row["assignments_by_pace"].values()
            for row in rows
            if row["mentor_id"] == mentor.id
        ]
        self.assertEqual(len(assigned), 2)

    def test_limits_four_mentors_per_pace(self):
        mentors = []
        for index in range(6):
            mentors.append(
                self._create_practice_mentor(
                    first_name=f"M{index}",
                    last_name="Pace",
                    email=f"m{index}@example.com",
                    pace="8-9",
                    selections=[self.practice_one],
                )
            )
        result = compute_mentor_schedule([self.practice_one])
        practice_row = result["practices"][0]
        assigned = practice_row["assignments_by_pace"].get("8-9", [])
        available = practice_row["available_by_pace"].get("8-9", [])
        self.assertEqual(len(assigned), 4)
        self.assertEqual(len(available), 2)
        self.assertEqual(practice_row["underfilled_pace_groups"], [])
        assigned_ids = {row["mentor_id"] for row in assigned}
        available_ids = {row["mentor_id"] for row in available}
        self.assertTrue(assigned_ids.isdisjoint(available_ids))
        self.assertEqual(assigned_ids | available_ids, {m.id for m in mentors})

    def test_reports_underfilled_pace_groups(self):
        self._create_practice_mentor(
            first_name="Solo",
            last_name="Runner",
            email="solo@example.com",
            pace="10-11",
            selections=[self.practice_one],
        )
        result = compute_mentor_schedule([self.practice_one])
        practice_row = result["practices"][0]
        self.assertEqual(
            practice_row["underfilled_pace_groups"],
            [{"pace": "10-11", "assigned_count": 1, "slots_remaining": 3}],
        )
        self.assertEqual(len(result["underfilled_practices"]), 1)
        self.assertEqual(
            result["underfilled_practices"][0]["underfilled_pace_groups"][0]["pace"],
            "10-11",
        )

    def test_moves_unassigned_selections_to_available(self):
        mentor = self._create_practice_mentor(
            first_name="Extra",
            last_name="Backup",
            email="extra@example.com",
            pace="11-12",
            selections=[self.practice_one, self.practice_two, self.practice_three],
        )
        result = compute_mentor_schedule(
            [self.practice_one, self.practice_two, self.practice_three]
        )
        assigned_practices = {
            practice_row["practice_id"]
            for practice_row in result["practices"]
            for rows in practice_row["assignments_by_pace"].values()
            for row in rows
            if row["mentor_id"] == mentor.id
        }
        available_practices = {
            practice_row["practice_id"]
            for practice_row in result["practices"]
            for rows in practice_row["available_by_pace"].values()
            for row in rows
            if row["mentor_id"] == mentor.id
        }
        self.assertEqual(len(assigned_practices), 2)
        self.assertEqual(len(available_practices), 1)
        self.assertTrue(assigned_practices.isdisjoint(available_practices))

    def test_lists_remote_mentors_separately(self):
        remote = Mentor.objects.create(
            first_name="Remote",
            last_name="Helper",
            email="remote@example.com",
            type=MentorTypes.REMOTE,
            pace="9-10",
        )
        remote.seasons.add(self.season)
        self.scheduled.sync_mentor_tokens()
        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=self.scheduled,
            mentor=remote,
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token,
            mentor=remote,
            practice=self.practice_one,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="9-10",
        )
        result = compute_mentor_schedule([self.practice_one])
        self.assertEqual(len(result["remote_mentors"]), 1)
        self.assertEqual(result["remote_mentors"][0]["mentor_id"], remote.id)
        assigned_remote = any(
            row["mentor_id"] == remote.id
            for practice_row in result["practices"]
            for rows in practice_row["assignments_by_pace"].values()
            for row in rows
        )
        self.assertFalse(assigned_remote)

    def test_api_preview_and_apply(self):
        mentor = self._create_practice_mentor(
            first_name="Apply",
            last_name="Me",
            email="apply@example.com",
            pace="12-13",
            selections=[self.practice_one],
        )
        response = self.client.post(
            "/api/practices/schedule-mentors/",
            {"practice_ids": [self.practice_one.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["assignment_rows"], 1)
        self.assertNotIn("applied", response.data)

        apply_without_schedule = self.client.post(
            "/api/practices/schedule-mentors/",
            {"practice_ids": [self.practice_one.id], "apply": True},
            format="json",
        )
        self.assertEqual(apply_without_schedule.status_code, 400)

        apply_response = self.client.post(
            "/api/practices/schedule-mentors/",
            {
                "practice_ids": [self.practice_one.id],
                "apply": True,
                "schedule": response.data,
            },
            format="json",
        )
        self.assertEqual(apply_response.status_code, 200)
        self.assertEqual(apply_response.data["applied"]["assigned"], 1)
        self.assertEqual(apply_response.data["applied"]["errors"], [])
        self.assertEqual(
            apply_response.data["applied"]["closed_practice_ids"],
            [self.practice_one.id],
        )
        detail = self.client.get(f"/api/practice/{self.practice_one.id}/")
        self.assertEqual(detail.status_code, 200)
        mentor_ids = {row["mentor_id"] for row in detail.data["mentor_replies"]}
        self.assertIn(mentor.id, mentor_ids)
        self.practice_one.refresh_from_db()
        self.assertIsNotNone(self.practice_one.mentor_selection_closed_at)

    def test_apply_rejects_stale_preview(self):
        mentor = self._create_practice_mentor(
            first_name="Pinned",
            last_name="Schedule",
            email="pinned@example.com",
            pace="11-12",
            selections=[self.practice_one],
        )
        preview = self.client.post(
            "/api/practices/schedule-mentors/",
            {"practice_ids": [self.practice_one.id]},
            format="json",
        )
        self.assertEqual(preview.status_code, 200)
        schedule = preview.json()

        ScheduledEmailMentorPracticeReply.objects.filter(
            mentor=mentor,
            practice=self.practice_one,
        ).update(attendance=PracticeAttendanceReply.NOT_ATTENDING)

        apply_response = self.client.post(
            "/api/practices/schedule-mentors/",
            {
                "practice_ids": [self.practice_one.id],
                "apply": True,
                "schedule": schedule,
            },
            format="json",
        )
        self.assertEqual(apply_response.status_code, 409)
        self.assertIn("out of date", apply_response.data["detail"])
        self.practice_one.refresh_from_db()
        self.assertIsNone(self.practice_one.mentor_selection_closed_at)

    def test_apply_accepts_string_practice_ids(self):
        mentor = self._create_practice_mentor(
            first_name="String",
            last_name="Ids",
            email="stringids@example.com",
            pace="10-11",
            selections=[self.practice_one],
        )
        preview = compute_mentor_schedule([self.practice_one])
        preview["practices"][0]["practice_id"] = str(self.practice_one.id)
        for rows in preview["practices"][0]["assignments_by_pace"].values():
            for row in rows:
                row["mentor_id"] = str(row["mentor_id"])

        apply_response = self.client.post(
            "/api/practices/schedule-mentors/",
            {
                "practice_ids": [str(self.practice_one.id)],
                "apply": True,
                "schedule": preview,
            },
            format="json",
        )
        self.assertEqual(apply_response.status_code, 200)
        self.assertEqual(apply_response.data["applied"]["assigned"], 1)
        detail = self.client.get(f"/api/practice/{self.practice_one.id}/")
        mentor_ids = {row["mentor_id"] for row in detail.data["mentor_replies"]}
        self.assertIn(mentor.id, mentor_ids)

    def test_validate_rejects_non_list_pace_rows(self):
        from tfk_mentors.mentor_scheduling import validate_schedule_payload

        error = validate_schedule_payload(
            {
                "practices": [
                    {
                        "practice_id": self.practice_one.id,
                        "assignments_by_pace": {"9-10": {"mentor_id": 1}},
                        "available_by_pace": {},
                    }
                ]
            },
            [self.practice_one.id],
        )
        self.assertIsNotNone(error)
        self.assertIn("must be lists", error)

    def test_apply_preserves_half_practice_attendance(self):
        mentor = self._create_practice_mentor(
            first_name="Half",
            last_name="Day",
            email="halfday@example.com",
            pace="9-10",
            selections=[self.practice_one],
        )
        ScheduledEmailMentorPracticeReply.objects.filter(
            mentor=mentor,
            practice=self.practice_one,
        ).update(attendance=PracticeAttendanceReply.FIRST_HALF)
        schedule = compute_mentor_schedule([self.practice_one])
        assigned = schedule["practices"][0]["assignments_by_pace"]["9-10"][0]
        self.assertEqual(assigned["attendance"], PracticeAttendanceReply.FIRST_HALF)

        from tfk_mentors.mentor_scheduling import apply_mentor_schedule

        applied = apply_mentor_schedule([self.practice_one], schedule)
        self.assertEqual(applied["assigned"], 1)
        self.assertEqual(applied["errors"], [])
        reply = ScheduledEmailMentorPracticeReply.objects.filter(
            mentor=mentor,
            practice=self.practice_one,
        ).latest("updated_at")
        self.assertEqual(reply.attendance, PracticeAttendanceReply.FIRST_HALF)

    def test_apply_does_not_close_practice_with_row_errors(self):
        good = self._create_practice_mentor(
            first_name="Good",
            last_name="Mentor",
            email="good@example.com",
            pace="9-10",
            selections=[self.practice_one],
        )
        schedule = {
            "practices": [
                {
                    "practice_id": self.practice_one.id,
                    "assignments_by_pace": {
                        "9-10": [
                            {"mentor_id": good.id, "pace": "9-10"},
                            {"mentor_id": good.id, "pace": "not-a-pace"},
                        ]
                    },
                    "available_by_pace": {},
                }
            ]
        }

        from tfk_mentors.mentor_scheduling import apply_mentor_schedule

        applied = apply_mentor_schedule([self.practice_one], schedule)
        self.assertEqual(applied["assigned"], 1)
        self.assertEqual(len(applied["errors"]), 1)
        self.assertEqual(applied["closed_practice_ids"], [])
        self.practice_one.refresh_from_db()
        self.assertIsNone(self.practice_one.mentor_selection_closed_at)

    def test_apply_empty_schedule_does_not_close_selection(self):
        empty = compute_mentor_schedule([self.practice_one])
        self.assertEqual(empty["summary"]["assignment_rows"], 0)

        from tfk_mentors.mentor_scheduling import apply_mentor_schedule

        applied = apply_mentor_schedule([self.practice_one], empty)
        self.assertEqual(applied["assigned"], 0)
        self.assertEqual(applied["available"], 0)
        self.assertEqual(applied["closed_practice_ids"], [])
        self.practice_one.refresh_from_db()
        self.assertIsNone(self.practice_one.mentor_selection_closed_at)

    def test_apply_rejects_invalid_pace(self):
        mentor = self._create_practice_mentor(
            first_name="Bad",
            last_name="Pace",
            email="badpace@example.com",
            pace="9-10",
            selections=[self.practice_one],
        )
        schedule = {
            "practices": [
                {
                    "practice_id": self.practice_one.id,
                    "assignments_by_pace": {
                        "not-a-pace": [
                            {
                                "mentor_id": mentor.id,
                                "pace": "not-a-pace",
                            }
                        ]
                    },
                    "available_by_pace": {},
                }
            ]
        }

        from tfk_mentors.mentor_scheduling import apply_mentor_schedule

        applied = apply_mentor_schedule([self.practice_one], schedule)
        self.assertEqual(applied["assigned"], 0)
        self.assertEqual(len(applied["errors"]), 1)
        self.assertEqual(applied["errors"][0]["action"], "assign")
        self.assertIn("Invalid pace", applied["errors"][0]["detail"])
        self.assertEqual(applied["closed_practice_ids"], [])
        self.practice_one.refresh_from_db()
        self.assertIsNone(self.practice_one.mentor_selection_closed_at)

    def test_apply_moves_overflow_to_available(self):
        mentor = self._create_practice_mentor(
            first_name="Busy",
            last_name="Mentor",
            email="busy@example.com",
            pace="9-10",
            selections=[self.practice_one, self.practice_two, self.practice_three],
        )
        schedule = compute_mentor_schedule(
            [self.practice_one, self.practice_two, self.practice_three]
        )
        self.assertEqual(schedule["summary"]["assignment_rows"], 2)
        self.assertEqual(schedule["summary"]["available_rows"], 1)

        from tfk_mentors.mentor_scheduling import apply_mentor_schedule

        applied = apply_mentor_schedule(
            [self.practice_one, self.practice_two, self.practice_three],
            schedule,
        )
        self.assertEqual(applied["assigned"], 2)
        self.assertEqual(applied["available"], 1)
        self.assertEqual(applied["errors"], [])
        self.assertEqual(
            set(applied["closed_practice_ids"]),
            {
                self.practice_one.id,
                self.practice_two.id,
                self.practice_three.id,
            },
        )

        attending_ids = set()
        available_ids = set()
        for practice in (self.practice_one, self.practice_two, self.practice_three):
            detail = self.client.get(f"/api/practice/{practice.id}/")
            self.assertEqual(detail.status_code, 200)
            attending_ids.update(
                row["mentor_id"] for row in detail.data["mentor_replies"]
            )
            available_ids.update(
                row["mentor_id"]
                for row in detail.data.get("available_mentor_replies", [])
            )
        self.assertIn(mentor.id, attending_ids)
        self.assertIn(mentor.id, available_ids)
        for practice in (self.practice_one, self.practice_two, self.practice_three):
            practice.refresh_from_db()
            self.assertIsNotNone(practice.mentor_selection_closed_at)
