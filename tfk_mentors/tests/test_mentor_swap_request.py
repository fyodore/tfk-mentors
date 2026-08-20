from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.mentor_swap_request import (
    approve_mentor_swap_request,
    build_mentor_swap_report,
    build_public_practice_swap_options,
    create_mentor_swap_request,
    mentor_swap_request_summary,
    reject_mentor_swap_request,
    send_rejected_swap_email,
    send_swap_request_email,
)
from tfk_mentors.models import (
    Coach,
    Mentor,
    MentorPracticeAssignment,
    MentorSwapRequest,
    MentorSwapRequestStatus,
    MentorTypes,
    PaceTypes,
    Practice,
    PracticeReminderEmail,
    PracticeReminderKind,
    Season,
    normalize_pace,
)
from tfk_mentors.practice_reminder import sync_practice_reminders_for_season


class MentorSwapRequestBaseTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

        self._email_patcher = patch(
            "tfk_mentors.mentor_swap_request._verify_email_delivery"
        )
        self._email_patcher.start()
        self.addCleanup(self._email_patcher.stop)

        self._notify_patcher = patch(
            "tfk_mentors.practice_swap_notification._verify_email_delivery"
        )
        self._notify_patcher.start()
        self.addCleanup(self._notify_patcher.stop)

        self.season = Season.objects.create(year=2026)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=3),
            season=self.season,
            full_practice=True,
            show_to_mentors=True,
        )
        self.outgoing = Mentor.objects.create(
            first_name="Out",
            last_name="Going",
            email="out@example.com",
            cell_phone="555-0100",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.TEN.value,
        )
        self.incoming = Mentor.objects.create(
            first_name="In",
            last_name="Coming",
            email="in@example.com",
            cell_phone="555-0101",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.EIGHT.value,
        )
        self.outgoing.seasons.add(self.season)
        self.incoming.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=self.outgoing,
            practice=self.practice,
            pace=self.outgoing.pace,
            is_available=False,
        )
        self.practice.mentors.add(self.outgoing)

    def _create_request(self):
        return create_mentor_swap_request(self.practice, self.outgoing, self.incoming)

    def _mark_last_reminder_sent(self, practice):
        Practice.objects.create(
            date=practice.date - timedelta(days=7),
            season=self.season,
            full_practice=True,
        )
        sync_practice_reminders_for_season(self.season)
        reminder = PracticeReminderEmail.objects.get(
            practice_one=practice,
            kind=PracticeReminderKind.AFTER_PRACTICE,
        )
        reminder.task_completed_at = timezone.now()
        reminder.save(update_fields=["task_completed_at"])
        return reminder


class BuildPublicPracticeSwapOptionsTests(MentorSwapRequestBaseTestCase):
    def test_lists_attending_and_eligible_incoming_mentors(self):
        options = build_public_practice_swap_options(self.practice)

        self.assertEqual(options["practice_id"], self.practice.id)
        self.assertEqual(options["season_year"], self.season.year)
        self.assertEqual(len(options["attending_mentors"]), 1)
        self.assertEqual(options["attending_mentors"][0]["mentor_id"], self.outgoing.id)
        incoming_ids = {row["mentor_id"] for row in options["incoming_mentors"]}
        self.assertIn(self.incoming.id, incoming_ids)
        self.assertNotIn(self.outgoing.id, incoming_ids)

    def test_excludes_mentors_without_valid_pace(self):
        no_pace = Mentor.objects.create(
            first_name="No",
            last_name="Pace",
            email="nopace@example.com",
            type=MentorTypes.PRACTICE,
            pace="",
        )
        no_pace.seasons.add(self.season)

        options = build_public_practice_swap_options(self.practice)
        incoming_ids = {row["mentor_id"] for row in options["incoming_mentors"]}
        self.assertNotIn(no_pace.id, incoming_ids)

    def test_excludes_mentors_from_other_seasons(self):
        other_season = Season.objects.create(year=2025)
        elsewhere = Mentor.objects.create(
            first_name="Else",
            last_name="Where",
            email="elsewhere@example.com",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        elsewhere.seasons.add(other_season)

        options = build_public_practice_swap_options(self.practice)
        incoming_ids = {row["mentor_id"] for row in options["incoming_mentors"]}
        self.assertNotIn(elsewhere.id, incoming_ids)

    def test_incoming_mentors_sorted_by_pace_then_name(self):
        faster = Mentor.objects.create(
            first_name="Zed",
            last_name="Aaa",
            email="zed@example.com",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.EIGHT.value,
        )
        faster.seasons.add(self.season)

        options = build_public_practice_swap_options(self.practice)
        incoming_names = [
            (row["last_name"], row["first_name"]) for row in options["incoming_mentors"]
        ]
        # Both incoming mentors share the same (fastest) pace; alphabetical by last name.
        self.assertEqual(incoming_names, [("Aaa", "Zed"), ("Coming", "In")])


class CreateMentorSwapRequestTests(MentorSwapRequestBaseTestCase):
    def test_creates_pending_request_and_sends_email(self):
        request_row, email_result = self._create_request()

        self.assertEqual(request_row.status, MentorSwapRequestStatus.PENDING)
        self.assertEqual(request_row.outgoing_mentor_id, self.outgoing.id)
        self.assertEqual(request_row.incoming_mentor_id, self.incoming.id)
        self.assertEqual(request_row.outgoing_pace, PaceTypes.TEN.value)
        self.assertEqual(request_row.incoming_pace, PaceTypes.EIGHT.value)
        self.assertEqual(email_result["sent"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.incoming.email])
        self.assertEqual(mail.outbox[0].subject, "Mentor Swap Request Approval")

    def test_rejects_same_mentor_for_both_sides(self):
        with self.assertRaises(ValidationError):
            create_mentor_swap_request(self.practice, self.outgoing, self.outgoing)

    def test_rejects_outgoing_not_assigned(self):
        not_assigned = Mentor.objects.create(
            first_name="Not",
            last_name="Assigned",
            email="notassigned@example.com",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        not_assigned.seasons.add(self.season)
        with self.assertRaises(ValidationError):
            create_mentor_swap_request(self.practice, not_assigned, self.incoming)

    def test_rejects_incoming_already_assigned(self):
        already = Mentor.objects.create(
            first_name="Already",
            last_name="Assigned",
            email="already@example.com",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        already.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=already,
            practice=self.practice,
            pace=already.pace,
            is_available=False,
        )
        self.practice.mentors.add(already)
        with self.assertRaises(ValidationError):
            create_mentor_swap_request(self.practice, self.outgoing, already)

    def test_rejects_incoming_not_in_season(self):
        other_season = Season.objects.create(year=2025)
        outsider = Mentor.objects.create(
            first_name="Out",
            last_name="Sider",
            email="outsider@example.com",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        outsider.seasons.add(other_season)
        with self.assertRaises(ValidationError):
            create_mentor_swap_request(self.practice, self.outgoing, outsider)

    def test_rejects_incoming_without_valid_pace(self):
        no_pace = Mentor.objects.create(
            first_name="No",
            last_name="Pace",
            email="nopace2@example.com",
            type=MentorTypes.PRACTICE,
            pace="",
        )
        no_pace.seasons.add(self.season)
        with self.assertRaises(ValidationError):
            create_mentor_swap_request(self.practice, self.outgoing, no_pace)

    def test_rejects_incoming_without_email(self):
        no_email = Mentor.objects.create(
            first_name="No",
            last_name="Email",
            email="",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        no_email.seasons.add(self.season)
        with self.assertRaises(ValidationError):
            create_mentor_swap_request(self.practice, self.outgoing, no_email)

    def test_rejects_when_practice_already_started(self):
        self.practice.date = timezone.now() - timedelta(minutes=5)
        self.practice.save(update_fields=["date", "updated_at"])
        with self.assertRaises(ValidationError):
            create_mentor_swap_request(self.practice, self.outgoing, self.incoming)

    def test_rejects_when_practice_hidden_from_mentors(self):
        self.practice.show_to_mentors = False
        self.practice.save(update_fields=["show_to_mentors", "updated_at"])
        with self.assertRaises(ValidationError):
            create_mentor_swap_request(self.practice, self.outgoing, self.incoming)

    def test_outgoing_pace_falls_back_to_mentor_pace_when_roster_pace_missing(self):
        self.outgoing.pace = ""
        self.outgoing.save(update_fields=["pace"])
        MentorPracticeAssignment.objects.filter(
            mentor=self.outgoing, practice=self.practice
        ).update(pace="")
        # A second attending mentor forces the roster loop to skip a non-matching
        # entry before reaching (and breaking on) the outgoing mentor.
        other_attendee = Mentor.objects.create(
            first_name="Other",
            last_name="Attendee",
            email="otherattendee@example.com",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        other_attendee.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=other_attendee,
            practice=self.practice,
            pace=other_attendee.pace,
            is_available=False,
        )
        self.practice.mentors.add(other_attendee)

        request_row, _email_result = self._create_request()
        self.assertEqual(request_row.outgoing_pace, "")

    def test_create_handles_email_send_failure_gracefully(self):
        with patch(
            "tfk_mentors.mentor_swap_request.send_mail",
            side_effect=RuntimeError("smtp down"),
        ):
            request_row, email_result = self._create_request()

        self.assertEqual(request_row.status, MentorSwapRequestStatus.PENDING)
        self.assertEqual(email_result["sent"], 0)
        self.assertEqual(email_result["error"], "smtp down")
        self.assertIn("approve_url", email_result)
        self.assertIn("reject_url", email_result)


class SwapRequestEmailHelperTests(MentorSwapRequestBaseTestCase):
    def test_send_swap_request_email_dry_run_does_not_send(self):
        request_row, _ = self._create_request()
        mail.outbox.clear()

        result = send_swap_request_email(request_row, dry_run=True)

        self.assertEqual(result["sent"], 0)
        self.assertFalse(result["skipped"])
        self.assertEqual(len(mail.outbox), 0)

    def test_send_swap_request_email_skips_when_incoming_has_no_email(self):
        request_row, _ = self._create_request()
        request_row.incoming_mentor.email = ""
        result = send_swap_request_email(request_row)

        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["recipients"], 0)
        self.assertTrue(result["skipped"])

    def test_send_rejected_swap_email_dry_run_does_not_send(self):
        request_row, _ = self._create_request()
        mail.outbox.clear()

        result = send_rejected_swap_email(request_row, dry_run=True)

        self.assertEqual(result["sent"], 0)
        self.assertFalse(result["skipped"])
        self.assertEqual(len(mail.outbox), 0)


class ApproveMentorSwapRequestTests(MentorSwapRequestBaseTestCase):
    def test_approve_swaps_mentor_and_sends_confirmations(self):
        request_row, _email_result = self._create_request()
        mail.outbox.clear()

        result = approve_mentor_swap_request(request_row)

        self.assertFalse(result["already_decided"])
        self.assertEqual(result["status"], MentorSwapRequestStatus.APPROVED)
        self.assertEqual(result["mentor_confirmations"]["sent"], 2)
        self.assertIsNone(result["coach_notification"])

        request_row.refresh_from_db()
        self.assertEqual(request_row.status, MentorSwapRequestStatus.APPROVED)
        self.assertIsNotNone(request_row.decided_at)

        self.practice.refresh_from_db()
        self.assertNotIn(self.outgoing, self.practice.mentors.all())
        self.assertIn(self.incoming, self.practice.mentors.all())

    def test_approve_is_idempotent_when_already_approved(self):
        request_row, _email_result = self._create_request()
        approve_mentor_swap_request(request_row)
        request_row.refresh_from_db()
        mail.outbox.clear()

        result = approve_mentor_swap_request(request_row)

        self.assertTrue(result["already_decided"])
        self.assertEqual(result["status"], MentorSwapRequestStatus.APPROVED)
        self.assertEqual(len(mail.outbox), 0)

    def test_approve_raises_when_already_rejected(self):
        request_row, _email_result = self._create_request()
        reject_mentor_swap_request(request_row, "no thanks")
        request_row.refresh_from_db()

        with self.assertRaises(ValidationError):
            approve_mentor_swap_request(request_row)

    def test_approve_backfills_missing_outgoing_pace(self):
        request_row, _email_result = self._create_request()
        request_row.outgoing_pace = ""
        request_row.save(update_fields=["outgoing_pace"])

        approve_mentor_swap_request(request_row)

        request_row.refresh_from_db()
        self.assertEqual(request_row.outgoing_pace, normalize_pace(self.outgoing.pace))

    def test_approve_sends_coach_notification_when_last_reminder_already_sent(self):
        coach = Coach.objects.create(
            first_name="Casey",
            last_name="Coach",
            email="casey@example.com",
        )
        coach.seasons.add(self.season)
        request_row, _email_result = self._create_request()
        self._mark_last_reminder_sent(self.practice)
        mail.outbox.clear()

        result = approve_mentor_swap_request(request_row)

        self.assertIsNotNone(result["coach_notification"])
        self.assertEqual(result["coach_notification"]["sent"], 1)

    def test_approve_revalidates_pair_and_raises_if_incoming_now_invalid(self):
        request_row, _email_result = self._create_request()
        # Incoming mentor gets assigned elsewhere on the same practice in the meantime.
        MentorPracticeAssignment.objects.create(
            mentor=self.incoming,
            practice=self.practice,
            pace=self.incoming.pace,
            is_available=False,
        )
        self.practice.mentors.add(self.incoming)

        with self.assertRaises(ValidationError):
            approve_mentor_swap_request(request_row)


class RejectMentorSwapRequestTests(MentorSwapRequestBaseTestCase):
    def test_reject_marks_rejected_and_sends_notification(self):
        request_row, _email_result = self._create_request()
        mail.outbox.clear()

        result = reject_mentor_swap_request(request_row, "Not a good fit")

        self.assertFalse(result["already_decided"])
        self.assertEqual(result["status"], MentorSwapRequestStatus.REJECTED)
        self.assertEqual(result["email"]["sent"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Rejected Mentor Swap")

        request_row.refresh_from_db()
        self.assertEqual(request_row.status, MentorSwapRequestStatus.REJECTED)
        self.assertEqual(request_row.reject_comments, "Not a good fit")
        self.assertIsNotNone(request_row.decided_at)

    def test_reject_is_idempotent_when_already_rejected(self):
        request_row, _email_result = self._create_request()
        reject_mentor_swap_request(request_row, "first reason")
        request_row.refresh_from_db()
        mail.outbox.clear()

        result = reject_mentor_swap_request(request_row, "second reason")

        self.assertTrue(result["already_decided"])
        self.assertEqual(result["status"], MentorSwapRequestStatus.REJECTED)
        self.assertEqual(len(mail.outbox), 0)
        request_row.refresh_from_db()
        self.assertEqual(request_row.reject_comments, "first reason")

    def test_reject_handles_email_send_failure_gracefully(self):
        request_row, _email_result = self._create_request()

        with patch(
            "tfk_mentors.mentor_swap_request.send_mail",
            side_effect=RuntimeError("smtp down"),
        ):
            result = reject_mentor_swap_request(request_row, "nope")

        self.assertFalse(result["already_decided"])
        self.assertEqual(result["email"]["sent"], 0)
        self.assertEqual(result["email"]["error"], "smtp down")
        request_row.refresh_from_db()
        self.assertEqual(request_row.status, MentorSwapRequestStatus.REJECTED)

    def test_reject_raises_when_already_approved(self):
        request_row, _email_result = self._create_request()
        approve_mentor_swap_request(request_row)
        request_row.refresh_from_db()

        with self.assertRaises(ValidationError):
            reject_mentor_swap_request(request_row, "too late")


class MentorSwapRequestSummaryAndReportTests(MentorSwapRequestBaseTestCase):
    def test_summary_contains_expected_fields(self):
        request_row, _email_result = self._create_request()

        summary = mentor_swap_request_summary(request_row)

        self.assertEqual(summary["id"], request_row.id)
        self.assertEqual(summary["status"], MentorSwapRequestStatus.PENDING)
        self.assertEqual(summary["token"], str(request_row.token))
        self.assertEqual(summary["practice_id"], self.practice.id)
        self.assertEqual(summary["season_year"], self.season.year)
        self.assertEqual(summary["outgoing_mentor"]["mentor_id"], self.outgoing.id)
        self.assertEqual(summary["incoming_mentor"]["mentor_id"], self.incoming.id)
        self.assertEqual(summary["reject_comments"], "")

    def test_report_excludes_pending_and_splits_approved_rejected(self):
        approved_row, _ = self._create_request()
        approve_mentor_swap_request(approved_row)
        approved_row.refresh_from_db()

        another_incoming = Mentor.objects.create(
            first_name="Another",
            last_name="Incoming",
            email="another@example.com",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        another_incoming.seasons.add(self.season)
        other_practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=5),
            season=self.season,
            full_practice=True,
            show_to_mentors=True,
        )
        other_outgoing = Mentor.objects.create(
            first_name="Other",
            last_name="Outgoing",
            email="otherout@example.com",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        other_outgoing.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=other_outgoing,
            practice=other_practice,
            pace=other_outgoing.pace,
            is_available=False,
        )
        other_practice.mentors.add(other_outgoing)
        rejected_row, _ = create_mentor_swap_request(
            other_practice, other_outgoing, another_incoming
        )
        reject_mentor_swap_request(rejected_row, "declined")
        rejected_row.refresh_from_db()

        pending_incoming = Mentor.objects.create(
            first_name="Pending",
            last_name="Incoming",
            email="pending@example.com",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.EIGHT.value,
        )
        pending_incoming.seasons.add(self.season)
        create_mentor_swap_request(other_practice, other_outgoing, pending_incoming)

        report = build_mentor_swap_report()

        approved_ids = {row["id"] for row in report["approved"]}
        rejected_ids = {row["id"] for row in report["rejected"]}
        self.assertEqual(approved_ids, {approved_row.id})
        self.assertEqual(rejected_ids, {rejected_row.id})

    def test_report_filters_by_season(self):
        approved_row, _ = self._create_request()
        approve_mentor_swap_request(approved_row)

        other_season = Season.objects.create(year=2030)
        report_for_other_season = build_mentor_swap_report(season_id=other_season.id)
        self.assertEqual(report_for_other_season["approved"], [])
        self.assertEqual(report_for_other_season["rejected"], [])

        report_for_this_season = build_mentor_swap_report(season_id=self.season.id)
        self.assertEqual(
            {row["id"] for row in report_for_this_season["approved"]},
            {approved_row.id},
        )


class PublicSwapOptionsApiTests(MentorSwapRequestBaseTestCase):
    def test_swap_options_endpoint_is_public_and_returns_options(self):
        anonymous_client = APIClient()
        response = anonymous_client.get(
            f"/api/public/practice/{self.practice.id}/swap-options/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["practice_id"], self.practice.id)
        incoming_ids = {row["mentor_id"] for row in response.data["incoming_mentors"]}
        self.assertIn(self.incoming.id, incoming_ids)

    def test_swap_options_endpoint_404_for_hidden_practice(self):
        self.practice.show_to_mentors = False
        self.practice.save(update_fields=["show_to_mentors", "updated_at"])
        anonymous_client = APIClient()
        response = anonymous_client.get(
            f"/api/public/practice/{self.practice.id}/swap-options/"
        )
        self.assertEqual(response.status_code, 404)

    def test_swap_options_endpoint_404_for_missing_practice(self):
        anonymous_client = APIClient()
        response = anonymous_client.get("/api/public/practice/999999/swap-options/")
        self.assertEqual(response.status_code, 404)


class PublicMentorSwapRequestApiTests(MentorSwapRequestBaseTestCase):
    def setUp(self):
        super().setUp()
        self.anon = APIClient()

    def test_create_endpoint_success(self):
        response = self.anon.post(
            "/api/public/mentor-swap-request/",
            {
                "practice": self.practice.id,
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], MentorSwapRequestStatus.PENDING)
        self.assertIn("email", response.data)
        self.assertTrue(
            MentorSwapRequest.objects.filter(
                practice=self.practice,
                outgoing_mentor=self.outgoing,
                incoming_mentor=self.incoming,
            ).exists()
        )

    def test_create_endpoint_validation_error_returns_400(self):
        response = self.anon.post(
            "/api/public/mentor-swap-request/",
            {
                "practice": self.practice.id,
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.outgoing.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.data)

    def test_create_endpoint_missing_fields_returns_400(self):
        response = self.anon.post(
            "/api/public/mentor-swap-request/",
            {"practice": self.practice.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_endpoint_not_found_returns_404(self):
        response = self.anon.post(
            "/api/public/mentor-swap-request/",
            {
                "practice": 999999,
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_detail_endpoint_returns_summary(self):
        request_row, _ = self._create_request()
        response = self.anon.get(
            f"/api/public/mentor-swap-request/{request_row.token}/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], request_row.id)

    def test_detail_endpoint_404_for_unknown_token(self):
        response = self.anon.get(
            "/api/public/mentor-swap-request/00000000-0000-0000-0000-000000000000/"
        )
        self.assertEqual(response.status_code, 404)

    def test_approve_endpoint_success(self):
        request_row, _ = self._create_request()
        response = self.anon.get(
            f"/api/public/mentor-swap-request/{request_row.token}/approve/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], MentorSwapRequestStatus.APPROVED)

        self.practice.refresh_from_db()
        self.assertIn(self.incoming, self.practice.mentors.all())

    def test_approve_endpoint_404_for_unknown_token(self):
        response = self.anon.get(
            "/api/public/mentor-swap-request/00000000-0000-0000-0000-000000000000/approve/"
        )
        self.assertEqual(response.status_code, 404)

    def test_approve_endpoint_400_when_already_rejected(self):
        request_row, _ = self._create_request()
        reject_mentor_swap_request(request_row, "no")
        response = self.anon.get(
            f"/api/public/mentor-swap-request/{request_row.token}/approve/"
        )
        self.assertEqual(response.status_code, 400)

    def test_reject_endpoint_success(self):
        request_row, _ = self._create_request()
        response = self.anon.post(
            f"/api/public/mentor-swap-request/{request_row.token}/reject/",
            {"comments": "Schedule conflict"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], MentorSwapRequestStatus.REJECTED)

        request_row.refresh_from_db()
        self.assertEqual(request_row.reject_comments, "Schedule conflict")

    def test_reject_endpoint_defaults_comments_to_empty_when_none(self):
        request_row, _ = self._create_request()
        response = self.anon.post(
            f"/api/public/mentor-swap-request/{request_row.token}/reject/",
            {"comments": None},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        request_row.refresh_from_db()
        self.assertEqual(request_row.reject_comments, "")

    def test_reject_endpoint_404_for_unknown_token(self):
        response = self.anon.post(
            "/api/public/mentor-swap-request/00000000-0000-0000-0000-000000000000/reject/",
            {"comments": "n/a"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_reject_endpoint_400_when_already_approved(self):
        request_row, _ = self._create_request()
        approve_mentor_swap_request(request_row)
        response = self.anon.post(
            f"/api/public/mentor-swap-request/{request_row.token}/reject/",
            {"comments": "too late"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class MentorSwapReportApiTests(MentorSwapRequestBaseTestCase):
    def test_report_endpoint_requires_site_authentication(self):
        anon = APIClient()
        response = anon.get("/api/reports/mentor-swaps/")
        self.assertEqual(response.status_code, 403)

    def test_report_endpoint_returns_approved_and_rejected(self):
        request_row, _ = self._create_request()
        approve_mentor_swap_request(request_row)

        response = self.client.get("/api/reports/mentor-swaps/")
        self.assertEqual(response.status_code, 200)
        approved_ids = {row["id"] for row in response.data["approved"]}
        self.assertIn(request_row.id, approved_ids)
        self.assertEqual(response.data["rejected"], [])

    def test_report_endpoint_filters_by_season_query_param(self):
        request_row, _ = self._create_request()
        approve_mentor_swap_request(request_row)
        other_season = Season.objects.create(year=2031)

        response = self.client.get(
            "/api/reports/mentor-swaps/", {"season": other_season.id}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["approved"], [])

    def test_report_endpoint_invalid_season_returns_400(self):
        response = self.client.get(
            "/api/reports/mentor-swaps/", {"season": "not-a-number"}
        )
        self.assertEqual(response.status_code, 400)
