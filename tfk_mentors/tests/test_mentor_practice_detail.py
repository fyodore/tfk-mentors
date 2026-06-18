from datetime import timedelta

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


class MentorPracticeDetailTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

        self.season = Season.objects.create(year=2026)
        self.other_season = Season.objects.create(year=2025)
        self.mentor = Mentor.objects.create(
            first_name="Pat",
            last_name="Mentor",
            email="pat@example.com",
            cell_phone="555-0100",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        self.mentor.seasons.add(self.season)

        self.assigned_practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=7),
            season=self.season,
            full_practice=True,
            nyrr_race="Long Run",
        )
        self.available_practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=14),
            season=self.season,
            full_practice=False,
        )
        self.direct_available_practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=21),
            season=self.season,
        )
        self.unassigned_practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=28),
            season=self.season,
        )
        Practice.objects.create(
            date=timezone.now() + timedelta(days=3),
            season=self.other_season,
        )

        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() + timedelta(days=1),
            body_text="Hello",
            recipient_season=self.season,
        )
        scheduled.practices.add(self.assigned_practice, self.available_practice)
        scheduled.sync_mentor_tokens()
        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=scheduled,
            mentor=self.mentor,
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token,
            mentor=self.mentor,
            practice=self.assigned_practice,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="9-10",
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token,
            mentor=self.mentor,
            practice=self.available_practice,
            attendance=PracticeAttendanceReply.AVAILABLE,
            pace="9-10",
        )
        self.assigned_practice.sync_mentor_assignments_from_replies()
        self.available_practice.sync_mentor_assignments_from_replies()

        MentorPracticeAssignment.objects.create(
            mentor=self.mentor,
            practice=self.direct_available_practice,
            pace="9-10",
            is_available=True,
        )
        self.direct_available_practice.mentors.remove(self.mentor)

    def test_mentor_practices_endpoint_lists_status_for_season_practices(self):
        response = self.client.get(f"/api/mentor/{self.mentor.id}/practices/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 4)
        by_id = {row["practice_id"]: row for row in response.data}

        self.assertEqual(by_id[self.assigned_practice.id]["status"], "assigned")
        self.assertEqual(by_id[self.assigned_practice.id]["pace"], "9-10")
        self.assertEqual(
            by_id[self.assigned_practice.id]["attendance"],
            PracticeAttendanceReply.ATTENDING,
        )

        self.assertEqual(by_id[self.available_practice.id]["status"], "available")
        self.assertEqual(
            by_id[self.available_practice.id]["attendance"],
            PracticeAttendanceReply.AVAILABLE,
        )

        direct_available = by_id[self.direct_available_practice.id]
        self.assertEqual(direct_available["status"], "available")
        self.assertEqual(direct_available["pace"], "9-10")

        self.assertIsNone(by_id[self.unassigned_practice.id]["status"])
        self.assertEqual(by_id[self.unassigned_practice.id]["pace"], "")

        self.assertEqual(response.data[0]["practice_id"], self.assigned_practice.id)
        self.assertEqual(response.data[1]["practice_id"], self.available_practice.id)
