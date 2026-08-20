import uuid
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
    build_live_practice_options,
    format_practice_label,
    maybe_mark_all_filled_on_open,
    practices_needing_mentors_for_mentor,
    send_underfilled_pace_emails,
    slots_remaining_for_pace,
    submit_practice_selections,
    submit_unavailable,
    thank_you_payload,
    underfilled_practice_rows_for_season,
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

    # -- Direct unit coverage for underfilled_pace_email helpers -----------

    def test_slots_remaining_for_pace_with_blank_pace_returns_zero(self):
        self.assertEqual(slots_remaining_for_pace(self.practice, ""), 0)
        self.assertEqual(slots_remaining_for_pace(self.practice, None), 0)

    def test_underfilled_practice_rows_for_season_direct(self):
        rows = underfilled_practice_rows_for_season(self.season.id)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["practice_id"], self.practice.id)
        self.assertEqual(row["label"], format_practice_label(self.practice))
        paces = {entry["pace"] for entry in row["underfilled_pace_groups"]}
        self.assertIn(PaceTypes.TEN.value, paces)
        self.assertIn(PaceTypes.EIGHT.value, paces)
        ten_entry = next(
            entry
            for entry in row["underfilled_pace_groups"]
            if entry["pace"] == PaceTypes.TEN.value
        )
        self.assertEqual(ten_entry["assigned_count"], 1)
        self.assertEqual(
            ten_entry["slots_remaining"], MIN_ASSIGNED_MENTORS_PER_PACE - 1
        )

    def test_underfilled_practice_rows_for_season_no_practices(self):
        other_season = Season.objects.create(year=2027)
        self.assertEqual(underfilled_practice_rows_for_season(other_season.id), [])

    def test_underfilled_practice_rows_for_season_none_includes_all_seasons(self):
        other_season = Season.objects.create(year=2027)
        other_practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=9),
            season=other_season,
            full_practice=True,
        )
        rows = underfilled_practice_rows_for_season(None)
        practice_ids = {row["practice_id"] for row in rows}
        self.assertIn(self.practice.id, practice_ids)
        self.assertIn(other_practice.id, practice_ids)

    def test_underfilled_practice_rows_for_season_skips_fully_staffed_practice(self):
        fully_staffed = Practice.objects.create(
            date=timezone.now() + timedelta(days=10),
            season=self.season,
            full_practice=True,
        )
        for pace_index, pace in enumerate(choice.value for choice in PaceTypes):
            for i in range(MIN_ASSIGNED_MENTORS_PER_PACE):
                mentor = Mentor.objects.create(
                    first_name=f"Staff{pace_index}{i}",
                    last_name="Full",
                    email=f"staff{pace_index}{i}@example.com",
                    type=MentorTypes.PRACTICE,
                    pace=pace,
                )
                mentor.seasons.add(self.season)
                MentorPracticeAssignment.objects.create(
                    mentor=mentor,
                    practice=fully_staffed,
                    pace=pace,
                    is_available=False,
                )
                fully_staffed.mentors.add(mentor)

        rows = underfilled_practice_rows_for_season(self.season.id)
        practice_ids = {row["practice_id"] for row in rows}
        self.assertNotIn(fully_staffed.id, practice_ids)
        self.assertIn(self.practice.id, practice_ids)

    def test_practices_needing_mentors_for_mentor_remote_type_returns_empty(self):
        self.assertEqual(
            practices_needing_mentors_for_mentor(self.remote, season_id=self.season.id),
            [],
        )

    def test_practices_needing_mentors_for_mentor_invalid_pace_returns_empty(self):
        no_pace_mentor = Mentor.objects.create(
            first_name="No",
            last_name="Pace",
            email="nopace@example.com",
            type=MentorTypes.PRACTICE,
            pace="",
        )
        no_pace_mentor.seasons.add(self.season)
        self.assertEqual(
            practices_needing_mentors_for_mentor(
                no_pace_mentor, season_id=self.season.id
            ),
            [],
        )

    def test_practices_needing_mentors_for_mentor_skips_full_pace(self):
        # Fill pace TEN to the minimum so it no longer needs mentors.
        for i in range(MIN_ASSIGNED_MENTORS_PER_PACE - 1):
            filler = Mentor.objects.create(
                first_name=f"Filler{i}",
                last_name="Ten",
                email=f"filler{i}@example.com",
                type=MentorTypes.PRACTICE,
                pace=PaceTypes.TEN.value,
            )
            filler.seasons.add(self.season)
            MentorPracticeAssignment.objects.create(
                mentor=filler,
                practice=self.practice,
                pace=PaceTypes.TEN.value,
                is_available=False,
            )
            self.practice.mentors.add(filler)

        self.assertEqual(
            practices_needing_mentors_for_mentor(
                self.eligible, season_id=self.season.id
            ),
            [],
        )

    def test_thank_you_payload_snagged_only_without_assigned(self):
        payload = thank_you_payload(snagged_labels=["Some Practice Label"])
        self.assertTrue(payload["completed"])
        messages = " ".join(payload["messages"])
        self.assertIn("someone snagged the slot for Some Practice Label", messages)
        self.assertIn("right before you.", messages)
        self.assertNotIn("You are assigned to", messages)

    def test_send_underfilled_pace_emails_requires_season_id(self):
        with self.assertRaisesMessage(
            ValueError, "Select a season to send underfilled pace emails."
        ):
            send_underfilled_pace_emails(season_id=None)

    def test_build_live_practice_options_empty_practice_ids(self):
        token = UnderfilledPaceMentorEmailToken.objects.create(
            send=UnderfilledPaceMentorEmailSend.objects.create(
                season=self.season, sent_at=timezone.now()
            ),
            mentor=self.eligible,
            sent_at=timezone.now(),
            practice_ids=[],
        )
        self.assertEqual(build_live_practice_options(token), [])

    def test_build_live_practice_options_skips_missing_practice(self):
        missing_id = self.practice.id + 999000
        self.assertFalse(Practice.objects.filter(id=missing_id).exists())
        token = UnderfilledPaceMentorEmailToken.objects.create(
            send=UnderfilledPaceMentorEmailSend.objects.create(
                season=self.season, sent_at=timezone.now()
            ),
            mentor=self.eligible,
            sent_at=timezone.now(),
            practice_ids=[missing_id],
        )
        self.assertEqual(build_live_practice_options(token), [])

    def test_build_live_practice_options_skips_already_assigned(self):
        token = UnderfilledPaceMentorEmailToken.objects.create(
            send=UnderfilledPaceMentorEmailSend.objects.create(
                season=self.season, sent_at=timezone.now()
            ),
            mentor=self.already_assigned,
            sent_at=timezone.now(),
            practice_ids=[self.practice.id],
        )
        self.assertEqual(build_live_practice_options(token), [])

    def test_build_live_practice_options_includes_filled_grayed_out(self):
        for i in range(MIN_ASSIGNED_MENTORS_PER_PACE - 1):
            filler = Mentor.objects.create(
                first_name=f"Gray{i}",
                last_name="Ten",
                email=f"gray{i}@example.com",
                type=MentorTypes.PRACTICE,
                pace=PaceTypes.TEN.value,
            )
            filler.seasons.add(self.season)
            MentorPracticeAssignment.objects.create(
                mentor=filler,
                practice=self.practice,
                pace=PaceTypes.TEN.value,
                is_available=False,
            )
            self.practice.mentors.add(filler)

        token = UnderfilledPaceMentorEmailToken.objects.create(
            send=UnderfilledPaceMentorEmailSend.objects.create(
                season=self.season, sent_at=timezone.now()
            ),
            mentor=self.eligible,
            sent_at=timezone.now(),
            practice_ids=[self.practice.id],
        )
        options = build_live_practice_options(token)
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0]["slots_remaining"], 0)
        self.assertFalse(options[0]["selectable"])

    def test_submit_unavailable_on_closed_token_raises(self):
        token = UnderfilledPaceMentorEmailToken.objects.create(
            send=UnderfilledPaceMentorEmailSend.objects.create(
                season=self.season, sent_at=timezone.now()
            ),
            mentor=self.eligible,
            sent_at=timezone.now(),
            practice_ids=[self.practice.id],
            responded_at=timezone.now(),
            response_type=UnderfilledPaceResponseType.UNAVAILABLE,
        )
        with self.assertRaisesMessage(ValueError, "no longer valid"):
            submit_unavailable(token)

    def test_submit_practice_selections_on_closed_token_raises(self):
        token = UnderfilledPaceMentorEmailToken.objects.create(
            send=UnderfilledPaceMentorEmailSend.objects.create(
                season=self.season, sent_at=timezone.now()
            ),
            mentor=self.eligible,
            sent_at=timezone.now(),
            practice_ids=[self.practice.id],
            responded_at=timezone.now(),
            response_type=UnderfilledPaceResponseType.UNAVAILABLE,
        )
        with self.assertRaisesMessage(ValueError, "no longer valid"):
            submit_practice_selections(token, [self.practice.id])

    def test_submit_practice_selections_filters_invalid_and_duplicate_ids(self):
        token = UnderfilledPaceMentorEmailToken.objects.create(
            send=UnderfilledPaceMentorEmailSend.objects.create(
                season=self.season, sent_at=timezone.now()
            ),
            mentor=self.eligible,
            sent_at=timezone.now(),
            practice_ids=[self.practice.id],
        )
        result = submit_practice_selections(
            token, [self.practice.id, self.practice.id, "not-an-int", None]
        )
        self.assertTrue(result["completed"])
        token.refresh_from_db()
        self.assertEqual(token.assigned_practice_ids, [self.practice.id])
        self.assertIn(self.eligible.id, self.practice.assigned_mentor_ids())

    def test_submit_practice_selections_empty_after_filtering_raises(self):
        token = UnderfilledPaceMentorEmailToken.objects.create(
            send=UnderfilledPaceMentorEmailSend.objects.create(
                season=self.season, sent_at=timezone.now()
            ),
            mentor=self.eligible,
            sent_at=timezone.now(),
            practice_ids=[self.practice.id],
        )
        with self.assertRaisesMessage(ValueError, "Select at least one practice"):
            submit_practice_selections(token, ["not-an-int", None])

    def test_submit_practice_selections_not_on_token_raises(self):
        other_practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=6),
            season=self.season,
            full_practice=True,
        )
        token = UnderfilledPaceMentorEmailToken.objects.create(
            send=UnderfilledPaceMentorEmailSend.objects.create(
                season=self.season, sent_at=timezone.now()
            ),
            mentor=self.eligible,
            sent_at=timezone.now(),
            practice_ids=[self.practice.id],
        )
        with self.assertRaisesMessage(ValueError, "not available"):
            submit_practice_selections(token, [other_practice.id])

    def test_submit_practice_selections_races_to_closed_token(self):
        token = UnderfilledPaceMentorEmailToken.objects.create(
            send=UnderfilledPaceMentorEmailSend.objects.create(
                season=self.season, sent_at=timezone.now()
            ),
            mentor=self.eligible,
            sent_at=timezone.now(),
            practice_ids=[self.practice.id],
        )
        # Simulate a concurrent request completing between the initial
        # is_open check and the locked re-fetch inside the transaction.
        UnderfilledPaceMentorEmailToken.objects.filter(pk=token.pk).update(
            responded_at=timezone.now(),
            response_type=UnderfilledPaceResponseType.UNAVAILABLE,
        )
        with self.assertRaisesMessage(ValueError, "no longer valid"):
            submit_practice_selections(token, [self.practice.id])

    def test_submit_practice_selections_snags_already_assigned_mentor(self):
        token = UnderfilledPaceMentorEmailToken.objects.create(
            send=UnderfilledPaceMentorEmailSend.objects.create(
                season=self.season, sent_at=timezone.now()
            ),
            mentor=self.already_assigned,
            sent_at=timezone.now(),
            practice_ids=[self.practice.id],
        )
        result = submit_practice_selections(token, [self.practice.id])
        self.assertTrue(result["completed"])
        messages = " ".join(result["messages"])
        self.assertIn("snagged", messages.lower())
        token.refresh_from_db()
        self.assertEqual(token.snagged_practice_ids, [self.practice.id])
        self.assertEqual(token.assigned_practice_ids, [])

    def test_submit_practice_selections_snags_missing_practice_id(self):
        missing_id = self.practice.id + 999000
        self.assertFalse(Practice.objects.filter(id=missing_id).exists())
        token = UnderfilledPaceMentorEmailToken.objects.create(
            send=UnderfilledPaceMentorEmailSend.objects.create(
                season=self.season, sent_at=timezone.now()
            ),
            mentor=self.eligible,
            sent_at=timezone.now(),
            practice_ids=[missing_id],
        )
        result = submit_practice_selections(token, [missing_id])
        self.assertTrue(result["completed"])
        token.refresh_from_db()
        self.assertEqual(token.snagged_practice_ids, [missing_id])
        self.assertEqual(token.assigned_practice_ids, [])

    def test_maybe_mark_all_filled_on_open_closed_token_returns_false(self):
        token = UnderfilledPaceMentorEmailToken.objects.create(
            send=UnderfilledPaceMentorEmailSend.objects.create(
                season=self.season, sent_at=timezone.now()
            ),
            mentor=self.eligible,
            sent_at=timezone.now(),
            practice_ids=[self.practice.id],
            responded_at=timezone.now(),
            response_type=UnderfilledPaceResponseType.UNAVAILABLE,
        )
        self.assertFalse(maybe_mark_all_filled_on_open(token, []))

    def test_maybe_mark_all_filled_on_open_with_open_slot_returns_false(self):
        token = UnderfilledPaceMentorEmailToken.objects.create(
            send=UnderfilledPaceMentorEmailSend.objects.create(
                season=self.season, sent_at=timezone.now()
            ),
            mentor=self.eligible,
            sent_at=timezone.now(),
            practice_ids=[self.practice.id],
        )
        options = [{"practice_id": self.practice.id, "slots_remaining": 2}]
        self.assertFalse(maybe_mark_all_filled_on_open(token, options))
        token.refresh_from_db()
        self.assertIsNone(token.responded_at)

    # -- API error path coverage --------------------------------------------

    def test_list_without_season_param_returns_all_sends(self):
        response = self.client.get("/api/underfilled-pace-email/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["sends"], [])

    def test_list_invalid_season_id_returns_400(self):
        response = self.client.get("/api/underfilled-pace-email/?season=not-a-number")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid season id", response.data["detail"])

    def test_list_season_not_found_returns_404(self):
        response = self.client.get("/api/underfilled-pace-email/?season=999999")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Season not found", response.data["detail"])

    def test_send_invalid_season_returns_400(self):
        response = self.client.post(
            "/api/underfilled-pace-email/send/",
            {"season": "not-a-number"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid season id", response.data["detail"])

    def test_reply_get_missing_token_returns_400(self):
        response = self.client.get("/api/underfilled-pace-reply/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Token is required", response.data["detail"])

    def test_reply_get_invalid_token_format_returns_400(self):
        response = self.client.get(
            "/api/underfilled-pace-reply/?token=not-a-valid-uuid"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid token", response.data["detail"])

    def test_reply_get_unknown_token_returns_404(self):
        response = self.client.get(
            f"/api/underfilled-pace-reply/{uuid.uuid4()}/"
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("invalid or has expired", response.data["detail"])

    def test_reply_put_unknown_token_returns_404(self):
        response = self.client.put(
            f"/api/underfilled-pace-reply/{uuid.uuid4()}/",
            {"unavailable": True},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("invalid or has expired", response.data["detail"])

    @patch("tfk_mentors.underfilled_pace_email._verify_email_delivery")
    def test_reply_put_both_unavailable_and_practice_ids_returns_400(
        self, _mock_verify
    ):
        self.client.post(
            "/api/underfilled-pace-email/send/",
            {"season": self.season.id},
            format="json",
        )
        token = UnderfilledPaceMentorEmailToken.objects.get(mentor=self.eligible)
        response = self.client.put(
            f"/api/underfilled-pace-reply/{token.token}/",
            {"unavailable": True, "practice_ids": [self.practice.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not both", response.data["detail"])

    @patch("tfk_mentors.underfilled_pace_email._verify_email_delivery")
    def test_reply_put_empty_practice_ids_returns_400(self, _mock_verify):
        self.client.post(
            "/api/underfilled-pace-email/send/",
            {"season": self.season.id},
            format="json",
        )
        token = UnderfilledPaceMentorEmailToken.objects.get(mentor=self.eligible)
        response = self.client.put(
            f"/api/underfilled-pace-reply/{token.token}/",
            {"practice_ids": []},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Select at least one practice", response.data["detail"])

    @patch("tfk_mentors.underfilled_pace_email._verify_email_delivery")
    def test_reply_put_practice_ids_not_a_list_returns_400(self, _mock_verify):
        self.client.post(
            "/api/underfilled-pace-email/send/",
            {"season": self.season.id},
            format="json",
        )
        token = UnderfilledPaceMentorEmailToken.objects.get(mentor=self.eligible)
        response = self.client.put(
            f"/api/underfilled-pace-reply/{token.token}/",
            {"practice_ids": self.practice.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("practice_ids must be a list", response.data["detail"])

    @patch("tfk_mentors.underfilled_pace_email._verify_email_delivery")
    def test_reply_put_practice_not_on_token_returns_400(self, _mock_verify):
        # Different season so it is never included in the eligible mentor's
        # token snapshot, guaranteeing it's "not on the token".
        other_season = Season.objects.create(year=2028)
        other_practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=6),
            season=other_season,
            full_practice=True,
        )
        self.client.post(
            "/api/underfilled-pace-email/send/",
            {"season": self.season.id},
            format="json",
        )
        token = UnderfilledPaceMentorEmailToken.objects.get(mentor=self.eligible)
        response = self.client.put(
            f"/api/underfilled-pace-reply/{token.token}/",
            {"practice_ids": [other_practice.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not available", response.data["detail"])

    @patch("tfk_mentors.underfilled_pace_email._verify_email_delivery")
    def test_list_includes_send_rows_after_sending(self, _mock_verify):
        self.client.post(
            "/api/underfilled-pace-email/send/",
            {"season": self.season.id},
            format="json",
        )
        response = self.client.get(
            f"/api/underfilled-pace-email/?season={self.season.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["sends"]), 1)
        send_row = response.data["sends"][0]
        self.assertEqual(send_row["season_id"], self.season.id)
        self.assertGreaterEqual(len(send_row["recipients"]), 1)
        recipient_ids = {row["mentor_id"] for row in send_row["recipients"]}
        self.assertIn(self.eligible.id, recipient_ids)

    @patch("tfk_mentors.underfilled_pace_email._verify_email_delivery")
    def test_send_without_season_uses_current_season(self, _mock_verify):
        response = self.client.post(
            "/api/underfilled-pace-email/send/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["sent"], 1)

    def test_send_without_season_and_no_current_season_returns_400(self):
        self.season.is_current = False
        self.season.save(update_fields=["is_current"])
        response = self.client.post(
            "/api/underfilled-pace-email/send/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("No current season is set", response.data["detail"])

    @patch("tfk_mentors.underfilled_pace_email._verify_email_delivery")
    def test_reply_get_completed_response_for_all_filled(self, _mock_verify):
        self.client.post(
            "/api/underfilled-pace-email/send/",
            {"season": self.season.id},
            format="json",
        )
        token = UnderfilledPaceMentorEmailToken.objects.get(mentor=self.eligible)
        for i in range(MIN_ASSIGNED_MENTORS_PER_PACE - 1):
            mentor = Mentor.objects.create(
                first_name=f"AllFilled{i}",
                last_name="Ten",
                email=f"allfilled{i}@example.com",
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

        # First GET marks the token as all_filled; second GET exercises the
        # already-closed / _completed_response all_filled branch.
        self.client.get(f"/api/underfilled-pace-reply/{token.token}/")
        response = self.client.get(f"/api/underfilled-pace-reply/{token.token}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["already_responded"])
        self.assertEqual(
            response.data["response_type"], UnderfilledPaceResponseType.ALL_FILLED
        )
        self.assertIn("fellow mentors", response.data["detail"])

    def test_reply_put_invalid_token_format_returns_400(self):
        response = self.client.put(
            "/api/underfilled-pace-reply/?token=not-a-valid-uuid",
            {"unavailable": True},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid token", response.data["detail"])

    @patch("tfk_mentors.underfilled_pace_email._verify_email_delivery")
    def test_reply_put_on_closed_token_returns_completed_response(
        self, _mock_verify
    ):
        self.client.post(
            "/api/underfilled-pace-email/send/",
            {"season": self.season.id},
            format="json",
        )
        token = UnderfilledPaceMentorEmailToken.objects.get(mentor=self.eligible)
        self.client.put(
            f"/api/underfilled-pace-reply/{token.token}/",
            {"unavailable": True},
            format="json",
        )
        response = self.client.put(
            f"/api/underfilled-pace-reply/{token.token}/",
            {"unavailable": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["already_responded"])
        self.assertIn("Thank you!", response.data["detail"])
