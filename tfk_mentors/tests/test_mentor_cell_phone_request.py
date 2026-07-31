from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import (
    Mentor,
    MentorCellPhoneRequestSend,
    MentorCellPhoneRequestToken,
    MentorPracticeAssignment,
    MentorTypes,
    PaceTypes,
    Practice,
    Season,
)


class MentorCellPhoneRequestTests(TestCase):
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
        self.missing = Mentor.objects.create(
            first_name="No",
            last_name="Phone",
            email="nophone@example.com",
            cell_phone="",
            type=MentorTypes.REMOTE,
            pace=PaceTypes.TEN.value,
        )
        self.with_phone = Mentor.objects.create(
            first_name="Has",
            last_name="Phone",
            email="hasphone@example.com",
            cell_phone="555-0100",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.ELEVEN.value,
        )
        self.missing.seasons.add(self.season)
        self.with_phone.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=self.missing,
            practice=self.practice,
            pace=self.missing.pace,
            is_available=False,
        )
        MentorPracticeAssignment.objects.create(
            mentor=self.with_phone,
            practice=self.practice,
            pace=self.with_phone.pace,
            is_available=False,
        )
        self.practice.mentors.add(self.missing, self.with_phone)

    def test_list_missing_assigned_mentors_without_cell_phone(self):
        response = self.client.get(
            f"/api/mentor-cell-phone-request/?season={self.season.id}"
        )
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.data["missing_mentors"]}
        self.assertIn(self.missing.id, ids)
        self.assertNotIn(self.with_phone.id, ids)

    @patch("tfk_mentors.cell_phone_request._verify_email_delivery")
    def test_send_emails_and_public_submit_invalidates_token(self, _mock_verify):
        send_response = self.client.post(
            "/api/mentor-cell-phone-request/send/",
            {"season": self.season.id},
            format="json",
        )
        self.assertEqual(send_response.status_code, 200)
        self.assertEqual(send_response.data["sent"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "TFK Mentor information needed")
        self.assertIn("/mentor-cell-phone?token=", mail.outbox[0].body)

        token = MentorCellPhoneRequestToken.objects.get(mentor=self.missing)
        self.assertIsNone(token.used_at)
        self.assertIn(str(token.token), mail.outbox[0].body)

        get_response = self.client.get(
            f"/api/mentor-cell-phone-update/{token.token}/"
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.data["first_name"], "No")

        put_response = self.client.put(
            f"/api/mentor-cell-phone-update/{token.token}/",
            {"cell_phone": "555-9999"},
            format="json",
        )
        self.assertEqual(put_response.status_code, 200)
        self.assertTrue(put_response.data["completed"])
        self.assertIn("Thank you", put_response.data["detail"])

        self.missing.refresh_from_db()
        token.refresh_from_db()
        self.assertEqual(self.missing.cell_phone, "555-9999")
        self.assertIsNotNone(token.used_at)

        reuse = self.client.get(f"/api/mentor-cell-phone-update/{token.token}/")
        self.assertEqual(reuse.status_code, 410)

        put_again = self.client.put(
            f"/api/mentor-cell-phone-update/{token.token}/",
            {"cell_phone": "555-0000"},
            format="json",
        )
        self.assertEqual(put_again.status_code, 410)

        list_response = self.client.get(
            f"/api/mentor-cell-phone-request/?season={self.season.id}"
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data["missing_mentors"], [])
        self.assertEqual(len(list_response.data["sends"]), 1)

    def test_send_with_no_missing_mentors_returns_400(self):
        self.missing.cell_phone = "555-1111"
        self.missing.save(update_fields=["cell_phone", "updated_at"])
        response = self.client.post(
            "/api/mentor-cell-phone-request/send/",
            {"season": self.season.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(MentorCellPhoneRequestSend.objects.count(), 0)

    def test_excludes_mentors_only_assigned_to_past_practices(self):
        past_practice = Practice.objects.create(
            date=timezone.now() - timedelta(days=5),
            season=self.season,
            full_practice=True,
        )
        past_only = Mentor.objects.create(
            first_name="Past",
            last_name="Only",
            email="pastonly@example.com",
            cell_phone="",
            type=MentorTypes.REMOTE,
            pace=PaceTypes.TEN.value,
        )
        past_only.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=past_only,
            practice=past_practice,
            pace=past_only.pace,
            is_available=False,
        )
        past_practice.mentors.add(past_only)

        both = Mentor.objects.create(
            first_name="Both",
            last_name="Practices",
            email="both@example.com",
            cell_phone="",
            type=MentorTypes.REMOTE,
            pace=PaceTypes.TEN.value,
        )
        both.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=both,
            practice=past_practice,
            pace=both.pace,
            is_available=False,
        )
        MentorPracticeAssignment.objects.create(
            mentor=both,
            practice=self.practice,
            pace=both.pace,
            is_available=False,
        )
        past_practice.mentors.add(both)
        self.practice.mentors.add(both)

        response = self.client.get(
            f"/api/mentor-cell-phone-request/?season={self.season.id}"
        )
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.data["missing_mentors"]}
        self.assertIn(self.missing.id, ids)
        self.assertIn(both.id, ids)
        self.assertNotIn(past_only.id, ids)
