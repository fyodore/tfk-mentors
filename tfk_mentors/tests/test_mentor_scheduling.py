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
        self.assertEqual(len(assigned), 4)
        self.assertEqual(practice_row["underfilled_pace_groups"], [])

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

    def test_moves_unassigned_selections_to_available_when_room(self):
        mentor = self._create_practice_mentor(
            first_name="Extra",
            last_name="Backup",
            email="extra@example.com",
            pace="11-12",
            selections=[self.practice_one, self.practice_two],
        )
        result = compute_mentor_schedule([self.practice_one, self.practice_two])
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
        self.assertEqual(len(assigned_practices), 1)
        self.assertEqual(len(available_practices), 1)

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

        apply_response = self.client.post(
            "/api/practices/schedule-mentors/",
            {"practice_ids": [self.practice_one.id], "apply": True},
            format="json",
        )
        self.assertEqual(apply_response.status_code, 200)
        self.assertEqual(apply_response.data["applied"]["assigned"], 1)
        detail = self.client.get(f"/api/practice/{self.practice_one.id}/")
        self.assertEqual(detail.status_code, 200)
        mentor_ids = {row["mentor_id"] for row in detail.data["mentor_replies"]}
        self.assertIn(mentor.id, mentor_ids)
