from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import (
    Mentor,
    MentorPracticeAssignment,
    MentorTypes,
    PaceTypes,
    Practice,
    Season,
    UnderfilledPaceMentorEmailSend,
    UnderfilledPaceMentorEmailToken,
    UnderfilledPaceResponseType,
)
from tfk_mentors.underfilled_pace_email import (
    MIN_ASSIGNED_MENTORS_PER_PACE,
    format_practice_label,
)


class UnderfilledPaceEmailTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

        self.season = Season.objects.create(year=2026, is_current=True)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=5),
            season=self.season,
            full_practice=True,
        )
        self.eligible = Mentor.objects.create(
            first_name="Eli",
            last_name="Gible",
            email="eligible@example.com",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.TEN.value,
        )
        self.already_assigned = Mentor.objects.create(
            first_name="Already",
            last_name="Assigned",
            email="assigned@example.com",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.TEN.value,
        )
        self.remote = Mentor.objects.create(
            first_name="Rem",
            last_name="Ote",
            email="remote@example.com",
            type=MentorTypes.REMOTE,
            pace=PaceTypes.TEN.value,
        )
        self.other_pace = Mentor.objects.create(
            first_name="Other",
            last_name="Pace",
            email="otherpace@example.com",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.EIGHT.value,
        )
        for mentor in (
            self.eligible,
            self.already_assigned,
            self.remote,
            self.other_pace,
        ):
            mentor.seasons.add(self.season)

        # Pace TEN has 1 assigned mentor (< 3); EIGHT has 0 so other_pace is also eligible.
        MentorPracticeAssignment.objects.create(
            mentor=self.already_assigned,
            practice=self.practice,
            pace=PaceTypes.TEN.value,
            is_available=False,
        )
        self.practice.mentors.add(self.already_assigned)

    def test_list_returns_sends_without_eligible_preview(self):
        response = self.client.get(
            f"/api/underfilled-pace-email/?season={self.season.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("sends", response.data)
        self.assertNotIn("eligible_mentors", response.data)
        self.assertEqual(response.data["sends"], [])

    @patch("tfk_mentors.underfilled_pace_email._verify_email_delivery")
    def test_dry_run_lists_eligible_at_practice_mentors(self, _mock_verify):
        response = self.client.post(
            "/api/underfilled-pace-email/send/",
            {"season": self.season.id, "dry_run": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.data["mentors"]}
        self.assertIn(self.eligible.id, ids)
        self.assertIn(self.other_pace.id, ids)
        self.assertNotIn(self.already_assigned.id, ids)
        self.assertNotIn(self.remote.id, ids)

        eligible_row = next(
            row for row in response.data["mentors"] if row["id"] == self.eligible.id
        )
        self.assertEqual(len(eligible_row["practices"]), 1)
        self.assertEqual(
            eligible_row["practices"][0]["slots_remaining"],
            MIN_ASSIGNED_MENTORS_PER_PACE - 1,
        )

    @patch("tfk_mentors.underfilled_pace_email._verify_email_delivery")
    def test_send_and_submit_practice_assignment(self, _mock_verify):
        send_response = self.client.post(
            "/api/underfilled-pace-email/send/",
            {"season": self.season.id},
            format="json",
        )
        self.assertEqual(send_response.status_code, 200)
        self.assertGreaterEqual(send_response.data["sent"], 1)
        self.assertTrue(mail.outbox)
        self.assertEqual(
            mail.outbox[0].subject,
            "Need for mentors at specific practices in your pace group",
        )
        self.assertIn("/underfilled-pace-reply?token=", mail.outbox[0].body)
        self.assertIn(format_practice_label(self.practice), mail.outbox[0].body)

        token = UnderfilledPaceMentorEmailToken.objects.get(mentor=self.eligible)
        self.assertIsNone(token.responded_at)
        self.assertIn(self.practice.id, token.practice_ids)

        get_response = self.client.get(
            f"/api/underfilled-pace-reply/{token.token}/"
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertFalse(get_response.data.get("completed"))
        self.assertEqual(len(get_response.data["practices"]), 1)

        put_response = self.client.put(
            f"/api/underfilled-pace-reply/{token.token}/",
            {"practice_ids": [self.practice.id]},
            format="json",
        )
        self.assertEqual(put_response.status_code, 200)
        self.assertTrue(put_response.data["completed"])
        self.assertIn("Thank you!", put_response.data["detail"])

        token.refresh_from_db()
        self.assertIsNotNone(token.responded_at)
        self.assertEqual(token.response_type, UnderfilledPaceResponseType.PRACTICES)
        self.assertIn(self.eligible.id, self.practice.assigned_mentor_ids())

        reuse = self.client.get(f"/api/underfilled-pace-reply/{token.token}/")
        self.assertEqual(reuse.status_code, 200)
        self.assertTrue(reuse.data["already_responded"])

    @patch("tfk_mentors.underfilled_pace_email._verify_email_delivery")
    def test_submit_unavailable(self, _mock_verify):
        self.client.post(
            "/api/underfilled-pace-email/send/",
            {"season": self.season.id},
            format="json",
        )
        token = UnderfilledPaceMentorEmailToken.objects.get(mentor=self.eligible)
        put_response = self.client.put(
            f"/api/underfilled-pace-reply/{token.token}/",
            {"unavailable": True},
            format="json",
        )
        self.assertEqual(put_response.status_code, 200)
        token.refresh_from_db()
        self.assertEqual(
            token.response_type, UnderfilledPaceResponseType.UNAVAILABLE
        )
        self.assertNotIn(self.eligible.id, self.practice.assigned_mentor_ids())

    @patch("tfk_mentors.underfilled_pace_email._verify_email_delivery")
    def test_all_filled_on_open_marks_responded(self, _mock_verify):
        self.client.post(
            "/api/underfilled-pace-email/send/",
            {"season": self.season.id},
            format="json",
        )
        token = UnderfilledPaceMentorEmailToken.objects.get(mentor=self.eligible)

        # Fill pace TEN to the minimum with other mentors.
        for i in range(MIN_ASSIGNED_MENTORS_PER_PACE - 1):
            mentor = Mentor.objects.create(
                first_name=f"Fill{i}",
                last_name="Ten",
                email=f"fill{i}@example.com",
                type=MentorTypes.PRACTICE,
                pace=PaceTypes.TEN.value,
            )
            mentor.seasons.add(self.season)
            MentorPracticeAssignment.objects.create(
                mentor=mentor,
                practice=self.practice,
                pace=PaceTypes.TEN.value,
                is_available=False,
            )
            self.practice.mentors.add(mentor)

        get_response = self.client.get(
            f"/api/underfilled-pace-reply/{token.token}/"
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertTrue(
            get_response.data.get("all_filled") or get_response.data.get("completed")
        )
        self.assertIn("fellow mentors", get_response.data["detail"])

        token.refresh_from_db()
        self.assertEqual(
            token.response_type, UnderfilledPaceResponseType.ALL_FILLED
        )
        self.assertIsNotNone(token.responded_at)

    @patch("tfk_mentors.underfilled_pace_email._verify_email_delivery")
    def test_race_snagged_partial_assign(self, _mock_verify):
        practice_b = Practice.objects.create(
            date=timezone.now() + timedelta(days=8),
            season=self.season,
            full_practice=True,
        )
        self.client.post(
            "/api/underfilled-pace-email/send/",
            {"season": self.season.id},
            format="json",
        )
        token = UnderfilledPaceMentorEmailToken.objects.get(mentor=self.eligible)
        self.assertIn(self.practice.id, token.practice_ids)
        self.assertIn(practice_b.id, token.practice_ids)

        # Fill first practice to 3 for TEN, leave practice_b open.
        for i in range(MIN_ASSIGNED_MENTORS_PER_PACE - 1):
            mentor = Mentor.objects.create(
                first_name=f"Snag{i}",
                last_name="Ten",
                email=f"snag{i}@example.com",
                type=MentorTypes.PRACTICE,
                pace=PaceTypes.TEN.value,
            )
            mentor.seasons.add(self.season)
            MentorPracticeAssignment.objects.create(
                mentor=mentor,
                practice=self.practice,
                pace=PaceTypes.TEN.value,
                is_available=False,
            )
            self.practice.mentors.add(mentor)

        put_response = self.client.put(
            f"/api/underfilled-pace-reply/{token.token}/",
            {"practice_ids": [self.practice.id, practice_b.id]},
            format="json",
        )
        self.assertEqual(put_response.status_code, 200)
        self.assertTrue(put_response.data["completed"])
        messages = " ".join(put_response.data.get("messages") or [])
        self.assertIn("snagged", messages.lower())
        self.assertIn(format_practice_label(practice_b), messages)
        self.assertIn(self.eligible.id, practice_b.assigned_mentor_ids())
        self.assertNotIn(self.eligible.id, self.practice.assigned_mentor_ids())

        token.refresh_from_db()
        self.assertEqual(token.snagged_practice_ids, [self.practice.id])
        self.assertEqual(token.assigned_practice_ids, [practice_b.id])

    def test_send_with_no_eligible_returns_400(self):
        # Remove all At Practice mentors from the season.
        for mentor in Mentor.objects.filter(type=MentorTypes.PRACTICE):
            mentor.seasons.clear()

        response = self.client.post(
            "/api/underfilled-pace-email/send/",
            {"season": self.season.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(UnderfilledPaceMentorEmailSend.objects.count(), 0)
