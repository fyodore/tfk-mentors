"""Focused coverage for views.py error paths and edge branches.

Complements the feature-focused test files (test_mentor_csv_import.py,
test_practice_mentor_available.py, test_mentor_email_reply.py, etc.) which
already exercise the happy paths for most views. This file targets the
remaining uncovered lines/branches: CSV helper edge cases, admin CRUD
error responses, and the various "not found" / "invalid input" branches
across the reports, scheduling, and public endpoints.
"""

import io
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import (
    Coach,
    Mentor,
    MentorCellPhoneRequestSend,
    MentorCellPhoneRequestToken,
    MentorPracticeAssignment,
    MentorTypes,
    PaceTypes,
    Practice,
    PracticeAttendanceReply,
    PracticeReminderEmail,
    ScheduledEmail,
    ScheduledEmailMentorPracticeReply,
    ScheduledEmailMentorToken,
    Season,
    ShowUpStatus,
)
from tfk_mentors.practice_reminder import sync_practice_reminders_for_season
from tfk_mentors.views import (
    build_practice_roster_report,
    email_response_pace_counts,
    email_shows_partial_month,
    mentor_pace_counts_from_rows,
    mentors_from_practice_replies,
    normalize_csv_header_key,
    normalize_csv_mentor_type,
    normalize_csv_row,
    open_csv_dict_reader,
    practice_mentor_result_payload,
    validate_practice_attendance,
    validate_reply_pace,
)


def authed_client():
    client = APIClient()
    session = client.session
    session["site_authenticated"] = True
    session.save()
    return client


class CsvHelperFunctionTests(TestCase):
    """Direct unit coverage for the small CSV normalization helpers."""

    def test_normalize_csv_header_key_none_returns_empty(self):
        self.assertEqual(normalize_csv_header_key(None), "")

    def test_normalize_csv_header_key_strips_and_lowers(self):
        self.assertEqual(normalize_csv_header_key(" First Name "), "first_name")

    def test_normalize_csv_row_skips_blank_header_keys(self):
        normalized = normalize_csv_row({"": "ignored", "Email": "a@example.com"})
        self.assertEqual(normalized, {"email": "a@example.com"})

    def test_normalize_csv_mentor_type_empty_returns_empty(self):
        self.assertEqual(normalize_csv_mentor_type(""), "")
        self.assertEqual(normalize_csv_mentor_type(None), "")

    def test_normalize_csv_mentor_type_matches_canonical_choice(self):
        self.assertEqual(normalize_csv_mentor_type("At Practice"), MentorTypes.PRACTICE)

    def test_normalize_csv_mentor_type_remote_variants(self):
        self.assertEqual(normalize_csv_mentor_type("r"), MentorTypes.REMOTE)
        self.assertEqual(normalize_csv_mentor_type("remotely"), MentorTypes.REMOTE)

    def test_normalize_csv_mentor_type_practice_variants(self):
        self.assertEqual(normalize_csv_mentor_type("in-person"), MentorTypes.PRACTICE)
        self.assertEqual(normalize_csv_mentor_type("practice group"), MentorTypes.PRACTICE)

    def test_normalize_csv_mentor_type_unrecognized_returned_as_is(self):
        self.assertEqual(normalize_csv_mentor_type("volunteer"), "volunteer")

    def test_open_csv_dict_reader_falls_back_to_excel_dialect(self):
        # A single-column, single-char body defeats csv.Sniffer's delimiter
        # detection, forcing the csv.Error except branch.
        reader = open_csv_dict_reader("a\n1\n")
        self.assertEqual(reader.fieldnames, ["a"])


class SeasonCreateCurrentTests(TestCase):
    def setUp(self):
        self.client = authed_client()

    def test_create_season_as_current_clears_other_current_seasons(self):
        existing = Season.objects.create(year=2025, is_current=True)
        response = self.client.post(
            "/api/season/",
            {"year": 2026, "is_current": True},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["is_current"])
        existing.refresh_from_db()
        self.assertFalse(existing.is_current)

    def test_create_season_without_is_current_leaves_others_untouched(self):
        existing = Season.objects.create(year=2025, is_current=True)
        response = self.client.post(
            "/api/season/", {"year": 2026}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["is_current"])
        existing.refresh_from_db()
        self.assertTrue(existing.is_current)


class CoachCsvImportTests(TestCase):
    def setUp(self):
        self.client = authed_client()
        self.season = Season.objects.create(year=2026)

    def _import_csv(self, body):
        upload = io.BytesIO(body.encode("utf-8"))
        upload.name = "coaches.csv"
        return self.client.post(
            "/api/coach/import-csv/",
            {"file": upload},
            format="multipart",
        )

    def test_missing_file_returns_400(self):
        response = self.client.post(
            "/api/coach/import-csv/", {}, format="multipart"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("CSV file is required", response.data["detail"])

    def test_bad_encoding_returns_400(self):
        upload = io.BytesIO(b"\xff\xfe\x00\x00bad")
        upload.name = "coaches.csv"
        response = self.client.post(
            "/api/coach/import-csv/",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("UTF-8", response.data["detail"])

    def test_missing_header_row_returns_400(self):
        response = self._import_csv("")
        self.assertEqual(response.status_code, 400)
        self.assertIn("header row", response.data["detail"])

    def test_missing_email_column_returns_400(self):
        response = self._import_csv("first_name,last_name\nA,B\n")
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data["detail"])

    def test_missing_season_year_reports_row_error(self):
        response = self._import_csv(
            "email,first_name,last_name\ncoach@example.com,A,B\n"
        )
        self.assertEqual(response.status_code, 207)
        self.assertTrue(
            any("season_year" in err for err in response.data["errors"])
        )
        self.assertFalse(Coach.objects.filter(email="coach@example.com").exists())

    def test_invalid_season_year_reports_row_error(self):
        response = self._import_csv(
            "email,season_year,first_name,last_name\n"
            "coach@example.com,notayear,A,B\n"
        )
        self.assertEqual(response.status_code, 207)
        self.assertTrue(
            any("invalid season year" in err for err in response.data["errors"])
        )

    def test_unknown_season_reports_row_error(self):
        response = self._import_csv(
            "email,season_year,first_name,last_name\n"
            "coach@example.com,1999,A,B\n"
        )
        self.assertEqual(response.status_code, 207)
        self.assertTrue(
            any("does not exist" in err for err in response.data["errors"])
        )

    def test_new_coach_missing_name_reports_row_error(self):
        response = self._import_csv(
            f"email,season_year,first_name,last_name\n"
            f"coach@example.com,{self.season.year},,\n"
        )
        self.assertEqual(response.status_code, 207)
        self.assertTrue(
            any(
                "first_name and last_name required" in err
                for err in response.data["errors"]
            )
        )
        self.assertFalse(Coach.objects.filter(email="coach@example.com").exists())

    def test_creates_new_coach_and_reports_created_by_season(self):
        response = self._import_csv(
            f"email,season_year,first_name,last_name,cell\n"
            f"coach@example.com,{self.season.year},Casey,Coach,555-0100\n"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created"], 1)
        self.assertEqual(
            response.data["created_by_season"][str(self.season.year)]
            if str(self.season.year) in response.data["created_by_season"]
            else response.data["created_by_season"][self.season.year],
            1,
        )
        coach = Coach.objects.get(email="coach@example.com")
        self.assertEqual(coach.first_name, "Casey")
        self.assertIn(self.season, coach.seasons.all())

    def test_updates_existing_coach_fields_and_adds_season(self):
        coach = Coach.objects.create(
            first_name="Old",
            last_name="Name",
            email="coach@example.com",
            cell="555-0000",
        )
        other_season = Season.objects.create(year=self.season.year - 1)
        coach.seasons.add(other_season)

        response = self._import_csv(
            f"email,season_year,first_name,last_name,cell\n"
            f"coach@example.com,{self.season.year},New,Name,555-9999\n"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["updated"], 1)
        coach.refresh_from_db()
        self.assertEqual(coach.first_name, "New")
        self.assertEqual(coach.cell, "555-9999")
        self.assertIn(self.season, coach.seasons.all())
        self.assertIn(other_season, coach.seasons.all())

    def test_blank_email_row_is_skipped(self):
        response = self._import_csv(
            f"email,season_year,first_name,last_name\n"
            f" ,{self.season.year},A,B\n"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["skipped"], 1)
        self.assertEqual(response.data["created"], 0)

    def test_update_existing_coach_with_identical_values_does_not_resave(self):
        coach = Coach.objects.create(
            first_name="Casey",
            last_name="Coach",
            email="coach@example.com",
            cell="555-0100",
        )
        response = self._import_csv(
            f"email,season_year,first_name,last_name,cell\n"
            f"coach@example.com,{self.season.year},Casey,Coach,555-0100\n"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["updated"], 1)
        coach.refresh_from_db()
        self.assertEqual(coach.cell, "555-0100")


class MentorCsvImportEdgeCaseTests(TestCase):
    def setUp(self):
        self.client = authed_client()
        self.season = Season.objects.create(year=2026)

    def _import_csv(self, body):
        upload = io.BytesIO(body.encode("utf-8"))
        upload.name = "mentors.csv"
        return self.client.post(
            "/api/mentor/import-csv/",
            {"file": upload},
            format="multipart",
        )

    def test_missing_file_returns_400(self):
        response = self.client.post(
            "/api/mentor/import-csv/", {}, format="multipart"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("CSV file is required", response.data["detail"])

    def test_bad_encoding_returns_400(self):
        upload = io.BytesIO(b"\xff\xfe\x00\x00bad")
        upload.name = "mentors.csv"
        response = self.client.post(
            "/api/mentor/import-csv/",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("UTF-8", response.data["detail"])

    def test_missing_header_row_returns_400(self):
        response = self._import_csv("")
        self.assertEqual(response.status_code, 400)
        self.assertIn("header row", response.data["detail"])

    def test_missing_email_column_returns_400(self):
        response = self._import_csv("first_name,last_name\nA,B\n")
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data["detail"])

    def test_missing_season_year_reports_row_error(self):
        response = self._import_csv(
            "email,first_name,last_name,type,pace,cell_phone\n"
            "runner@example.com,Jane,Doe,At Practice,8-9,5551234567\n"
        )
        self.assertEqual(response.status_code, 207)
        self.assertTrue(
            any("season_year" in err for err in response.data["errors"])
        )

    def test_invalid_season_year_reports_row_error(self):
        response = self._import_csv(
            "email,season_year,first_name,last_name,type,pace,cell_phone\n"
            "runner@example.com,notayear,Jane,Doe,At Practice,8-9,5551234567\n"
        )
        self.assertEqual(response.status_code, 207)
        self.assertTrue(
            any("invalid season year" in err for err in response.data["errors"])
        )

    def test_unknown_season_reports_row_error(self):
        response = self._import_csv(
            "email,season_year,first_name,last_name,type,pace,cell_phone\n"
            "runner@example.com,1999,Jane,Doe,At Practice,8-9,5551234567\n"
        )
        self.assertEqual(response.status_code, 207)
        self.assertTrue(
            any("does not exist" in err for err in response.data["errors"])
        )

    def test_invalid_type_reports_row_error(self):
        response = self._import_csv(
            f"email,season_year,first_name,last_name,type,pace,cell_phone\n"
            f"runner@example.com,{self.season.year},Jane,Doe,SomethingWeird,8-9,5551234567\n"
        )
        self.assertEqual(response.status_code, 207)
        self.assertTrue(any("invalid type" in err for err in response.data["errors"]))

    def test_new_mentor_missing_cell_phone_detail_mentions_type(self):
        response = self._import_csv(
            f"email,season_year,first_name,last_name,type,pace\n"
            f"runner@example.com,{self.season.year},Jane,Doe,At Practice,8-9\n"
        )
        self.assertEqual(response.status_code, 207)
        detail = response.data["errors"][0]
        self.assertIn("cell_phone", detail)
        self.assertIn("At Practice", detail)

    def test_new_mentor_missing_cell_phone_no_type_column(self):
        response = self._import_csv(
            f"email,season_year,first_name,last_name,pace\n"
            f"runner@example.com,{self.season.year},Jane,Doe,8-9\n"
        )
        self.assertEqual(response.status_code, 207)
        detail = response.data["errors"][0]
        self.assertIn("cell_phone", detail)
        self.assertIn("type column is missing", detail)

    def test_blank_email_row_is_skipped(self):
        response = self._import_csv(
            f"email,season_year,first_name,last_name,type\n"
            f" ,{self.season.year},Jane,Doe,Remote\n"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["skipped"], 1)
        self.assertEqual(response.data["created"], 0)

    def test_new_remote_mentor_missing_last_name_reports_error_without_cell_phone_note(
        self,
    ):
        response = self._import_csv(
            f"email,season_year,first_name,type\n"
            f"remote-noname@example.com,{self.season.year},Pat,Remote\n"
        )
        self.assertEqual(response.status_code, 207)
        detail = response.data["errors"][0]
        self.assertIn("last_name", detail)
        self.assertNotIn("cell_phone", detail)

    def test_update_existing_at_practice_mentor_keeps_pace_when_omitted(self):
        mentor = Mentor.objects.create(
            first_name="Jane",
            last_name="Doe",
            email="runner@example.com",
            cell_phone="5551234567",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        mentor.seasons.add(self.season)
        response = self._import_csv(
            f"email,season_year,first_name,last_name,type\n"
            f"runner@example.com,{self.season.year},Jane,Doe,At Practice\n"
        )
        self.assertEqual(response.status_code, 200)
        mentor.refresh_from_db()
        self.assertEqual(mentor.pace, "9-10")

    def test_update_existing_remote_mentor_cell_phone_unchanged_when_equal(self):
        mentor = Mentor.objects.create(
            first_name="Pat",
            last_name="Lee",
            email="remote@example.com",
            cell_phone="",
            type=MentorTypes.REMOTE,
            pace="",
        )
        mentor.seasons.add(self.season)
        response = self._import_csv(
            f"email,season_year,first_name,last_name,type\n"
            f"remote@example.com,{self.season.year},Pat,Lee,Remote\n"
        )
        self.assertEqual(response.status_code, 200)
        mentor.refresh_from_db()
        self.assertEqual(mentor.cell_phone, "")
        self.assertEqual(response.data["updated"], 1)

    def test_update_existing_at_practice_mentor_missing_pace_reports_error(self):
        mentor = Mentor.objects.create(
            first_name="Jane",
            last_name="Doe",
            email="runner@example.com",
            cell_phone="5551234567",
            type=MentorTypes.PRACTICE,
            pace="",
        )
        mentor.seasons.add(self.season)
        response = self._import_csv(
            f"email,season_year,first_name,last_name,type\n"
            f"runner@example.com,{self.season.year},Jane,Doe,At Practice\n"
        )
        self.assertEqual(response.status_code, 207)
        self.assertTrue(
            any("pace is required" in err for err in response.data["errors"])
        )

    def test_update_existing_at_practice_mentor_missing_cell_phone_reports_error(self):
        mentor = Mentor.objects.create(
            first_name="Jane",
            last_name="Doe",
            email="runner@example.com",
            cell_phone="",
            type=MentorTypes.PRACTICE,
            pace="8-9",
        )
        mentor.seasons.add(self.season)
        response = self._import_csv(
            f"email,season_year,first_name,last_name,type,pace\n"
            f"runner@example.com,{self.season.year},Jane,Doe,At Practice,8-9\n"
        )
        self.assertEqual(response.status_code, 207)
        self.assertTrue(
            any("cell phone is required" in err for err in response.data["errors"])
        )

    def test_update_existing_mentor_split_practice_flag_changes(self):
        mentor = Mentor.objects.create(
            first_name="Jane",
            last_name="Doe",
            email="runner@example.com",
            cell_phone="5551234567",
            type=MentorTypes.PRACTICE,
            pace="8-9",
            split_practice=False,
        )
        mentor.seasons.add(self.season)
        response = self._import_csv(
            f"email,season_year,first_name,last_name,type,pace,split_practice\n"
            f"runner@example.com,{self.season.year},Jane,Doe,At Practice,8-9,true\n"
        )
        self.assertEqual(response.status_code, 200)
        mentor.refresh_from_db()
        self.assertTrue(mentor.split_practice)

    def test_update_existing_mentor_no_changes_still_counts_as_updated(self):
        mentor = Mentor.objects.create(
            first_name="Jane",
            last_name="Doe",
            email="runner@example.com",
            cell_phone="5551234567",
            type=MentorTypes.PRACTICE,
            pace="8-9",
            split_practice=False,
        )
        mentor.seasons.add(self.season)
        response = self._import_csv(
            f"email,season_year,first_name,last_name,type,pace\n"
            f"runner@example.com,{self.season.year},Jane,Doe,At Practice,8-9\n"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["updated"], 1)


class PracticeViewSetCrudEdgeTests(TestCase):
    def setUp(self):
        self.client = authed_client()
        self.season = Season.objects.create(year=2026)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=7),
            season=self.season,
            full_practice=True,
        )

    def test_retrieve_with_basic_query_param_uses_basic_serializer(self):
        response = self.client.get(f"/api/practice/{self.practice.id}/?basic=1")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("mentor_replies", response.data)

    def test_patch_practice_syncs_reminders(self):
        with patch(
            "tfk_mentors.views.sync_practice_reminders_for_season"
        ) as mock_sync:
            response = self.client.patch(
                f"/api/practice/{self.practice.id}/",
                {"nyrr_race": "Updated Race"},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        mock_sync.assert_called_with(self.practice.season_id)

    def test_delete_practice_syncs_reminders_for_season(self):
        season_id = self.practice.season_id
        with patch(
            "tfk_mentors.views.sync_practice_reminders_for_season"
        ) as mock_sync:
            response = self.client.delete(f"/api/practice/{self.practice.id}/")
        self.assertEqual(response.status_code, 204)
        mock_sync.assert_called_with(season_id)
        self.assertFalse(Practice.objects.filter(pk=self.practice.id).exists())


class PracticeMentorRepliesErrorTests(TestCase):
    def setUp(self):
        self.client = authed_client()
        self.season = Season.objects.create(year=2026)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=7),
            season=self.season,
            full_practice=True,
        )
        self.mentor = Mentor.objects.create(
            first_name="Pat",
            last_name="Mentor",
            email="pat@example.com",
            cell_phone="555-0100",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.TEN.value,
        )
        self.mentor.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=self.mentor,
            practice=self.practice,
            pace=self.mentor.pace,
            is_available=False,
        )
        self.practice.mentors.add(self.mentor)

    def _url(self):
        return f"/api/practice/{self.practice.id}/mentor-replies/"

    def test_patch_invalid_mentor_id_returns_400(self):
        response = self.client.patch(
            self._url(), {"mentor": "abc", "pace": "8-9"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid mentor id", response.data["detail"])

    def test_patch_mentor_not_found_returns_404(self):
        response = self.client.patch(
            self._url(), {"mentor": 999999, "pace": "8-9"}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_patch_invalid_pace_choice_returns_400(self):
        response = self.client.patch(
            self._url(),
            {"mentor": self.mentor.id, "pace": "not-a-pace"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid pace choice", response.data["detail"])

    def test_patch_update_mentor_pace_validation_error_returns_400(self):
        from django.core.exceptions import ValidationError

        with patch(
            "tfk_mentors.views.Practice.update_mentor_pace",
            side_effect=ValidationError("pace conflict"),
        ):
            response = self.client.patch(
                self._url(),
                {"mentor": self.mentor.id, "pace": "8-9"},
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("pace conflict", response.data["detail"])

    def test_patch_pace_for_mentor_not_on_practice_returns_400(self):
        outsider = Mentor.objects.create(
            first_name="Out",
            last_name="Sider",
            email="outsider@example.com",
            cell_phone="555-0199",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        outsider.seasons.add(self.season)
        response = self.client.patch(
            self._url(),
            {"mentor": outsider.id, "pace": "9-10"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not assigned to this practice", response.data["detail"])

    def test_patch_without_pace_or_available_returns_400(self):
        response = self.client.patch(
            self._url(),
            {"mentor": self.mentor.id, "attendance": "not_attending"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Provide a valid pace or attendance", response.data["detail"])

    def test_patch_available_for_mentor_not_on_roster_returns_400(self):
        outsider = Mentor.objects.create(
            first_name="Out",
            last_name="Sider",
            email="outsider2@example.com",
            cell_phone="555-0198",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        outsider.seasons.add(self.season)
        response = self.client.patch(
            self._url(),
            {"mentor": outsider.id, "attendance": "available"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not assigned to this practice", response.data["detail"])

    def test_post_invalid_mentor_id_returns_400(self):
        response = self.client.post(
            self._url(), {"mentor": "abc", "pace": "8-9"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid mentor id", response.data["detail"])

    def test_post_mentor_not_found_returns_404(self):
        response = self.client.post(
            self._url(), {"mentor": 999999, "pace": "8-9"}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_post_mentor_outside_season_returns_400(self):
        other_season = Season.objects.create(year=2020)
        outsider = Mentor.objects.create(
            first_name="Out",
            last_name="Season",
            email="outseason@example.com",
            cell_phone="555-0197",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        outsider.seasons.add(other_season)
        response = self.client.post(
            self._url(), {"mentor": outsider.id, "pace": "9-10"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("must belong to the practice season", response.data["detail"])

    def test_post_invalid_pace_choice_returns_400(self):
        other = Mentor.objects.create(
            first_name="An",
            last_name="Other",
            email="another@example.com",
            cell_phone="555-0196",
            type=MentorTypes.PRACTICE,
            pace="not-a-pace",
        )
        other.seasons.add(self.season)
        response = self.client.post(
            self._url(), {"mentor": other.id, "pace": ""}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid pace choice", response.data["detail"])

    def test_post_mark_mentor_attending_validation_error_returns_400(self):
        from django.core.exceptions import ValidationError

        other = Mentor.objects.create(
            first_name="An",
            last_name="Other",
            email="another3@example.com",
            cell_phone="555-0194",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        other.seasons.add(self.season)
        with patch(
            "tfk_mentors.views.Practice.mark_mentor_attending",
            side_effect=ValidationError("cannot attend"),
        ):
            response = self.client.post(
                self._url(), {"mentor": other.id, "pace": "9-10"}, format="json"
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot attend", response.data["detail"])

    def test_post_integrity_error_returns_400(self):
        other = Mentor.objects.create(
            first_name="An",
            last_name="Other",
            email="another2@example.com",
            cell_phone="555-0195",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        other.seasons.add(self.season)
        with patch(
            "tfk_mentors.views.Practice.mark_mentor_attending",
            side_effect=__import__("django.db", fromlist=["IntegrityError"]).IntegrityError(
                "conflict"
            ),
        ):
            response = self.client.post(
                self._url(), {"mentor": other.id, "pace": "9-10"}, format="json"
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("database conflict", response.data["detail"])

    def test_delete_invalid_mentor_id_returns_400(self):
        response = self.client.delete(self._url() + "?mentor=abc")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid mentor id", response.data["detail"])


class SwapMentorErrorTests(TestCase):
    def setUp(self):
        self.client = authed_client()
        self.season = Season.objects.create(year=2026)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=3),
            season=self.season,
            full_practice=True,
        )
        self.outgoing = Mentor.objects.create(
            first_name="Out",
            last_name="Going",
            email="out@example.com",
            cell_phone="555-0100",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.TEN.value,
        )
        self.outgoing.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=self.outgoing,
            practice=self.practice,
            pace=self.outgoing.pace,
            is_available=False,
        )
        self.practice.mentors.add(self.outgoing)

    def _url(self):
        return f"/api/practice/{self.practice.id}/swap-mentor/"

    def test_missing_ids_returns_400(self):
        response = self.client.post(self._url(), {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("outgoing_mentor and incoming_mentor", response.data["detail"])

    def test_unknown_mentor_returns_404(self):
        response = self.client.post(
            self._url(),
            {"outgoing_mentor": self.outgoing.id, "incoming_mentor": 999999},
            format="json",
        )
        self.assertEqual(response.status_code, 404)


class ViewHelperFunctionTests(TestCase):
    """Direct coverage for standalone helper functions used by the reports."""

    def setUp(self):
        self.season = Season.objects.create(year=2026)

    def test_validate_practice_attendance_rejects_unknown_choice(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=self.season,
            full_practice=True,
        )
        mentor = Mentor.objects.create(
            first_name="A",
            last_name="B",
            email="ab@example.com",
            type=MentorTypes.PRACTICE,
        )
        with self.assertRaises(ValueError):
            validate_practice_attendance(practice, mentor, "bogus")

    def test_validate_practice_attendance_available_short_circuits(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=self.season,
            full_practice=True,
        )
        mentor = Mentor.objects.create(
            first_name="A",
            last_name="B",
            email="ab2@example.com",
            type=MentorTypes.REMOTE,
        )
        validate_practice_attendance(
            practice, mentor, PracticeAttendanceReply.AVAILABLE
        )

    def test_validate_practice_attendance_remote_rejects_half_practice(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=self.season,
            full_practice=True,
        )
        mentor = Mentor.objects.create(
            first_name="A",
            last_name="B",
            email="ab3@example.com",
            type=MentorTypes.REMOTE,
        )
        with self.assertRaises(ValueError):
            validate_practice_attendance(
                practice, mentor, PracticeAttendanceReply.FIRST_HALF
            )

    def test_validate_practice_attendance_full_practice_rejects_half(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=self.season,
            full_practice=True,
        )
        mentor = Mentor.objects.create(
            first_name="A",
            last_name="B",
            email="ab4@example.com",
            type=MentorTypes.PRACTICE,
            split_practice=True,
        )
        with self.assertRaises(ValueError):
            validate_practice_attendance(
                practice, mentor, PracticeAttendanceReply.FIRST_HALF
            )

    def test_validate_practice_attendance_split_practice_rejects_full_attending(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=self.season,
            full_practice=False,
        )
        mentor = Mentor.objects.create(
            first_name="A",
            last_name="B",
            email="ab5@example.com",
            type=MentorTypes.PRACTICE,
            split_practice=True,
        )
        with self.assertRaises(ValueError):
            validate_practice_attendance(
                practice, mentor, "bogus-half-choice"
            )

    def test_validate_practice_attendance_non_split_rejects_half(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=self.season,
            full_practice=False,
        )
        mentor = Mentor.objects.create(
            first_name="A",
            last_name="B",
            email="ab6@example.com",
            type=MentorTypes.PRACTICE,
            split_practice=False,
        )
        with self.assertRaises(ValueError):
            validate_practice_attendance(
                practice, mentor, PracticeAttendanceReply.FIRST_HALF
            )

    def test_validate_reply_pace_extra_pace_for_non_pace_attendance_rejected(self):
        mentor = Mentor.objects.create(
            first_name="A",
            last_name="B",
            email="ab7@example.com",
            type=MentorTypes.PRACTICE,
        )
        with self.assertRaises(ValueError):
            validate_reply_pace(
                mentor, PracticeAttendanceReply.NOT_ATTENDING, "8-9"
            )

    def test_validate_reply_pace_remote_missing_pace_rejected(self):
        mentor = Mentor.objects.create(
            first_name="A",
            last_name="B",
            email="ab8@example.com",
            type=MentorTypes.REMOTE,
        )
        with self.assertRaises(ValueError):
            validate_reply_pace(mentor, PracticeAttendanceReply.ATTENDING, "")

    def test_validate_reply_pace_remote_invalid_pace_rejected(self):
        mentor = Mentor.objects.create(
            first_name="A",
            last_name="B",
            email="ab9@example.com",
            type=MentorTypes.REMOTE,
        )
        with self.assertRaises(ValueError):
            validate_reply_pace(
                mentor, PracticeAttendanceReply.ATTENDING, "not-a-pace"
            )

    def test_validate_reply_pace_at_practice_invalid_pace_rejected(self):
        mentor = Mentor.objects.create(
            first_name="A",
            last_name="B",
            email="ab10@example.com",
            type=MentorTypes.PRACTICE,
        )
        with self.assertRaises(ValueError):
            validate_reply_pace(
                mentor, PracticeAttendanceReply.ATTENDING, "not-a-pace"
            )

    def test_email_shows_partial_month_true_when_not_full_span(self):
        season = self.season
        practice = Practice.objects.create(
            date=timezone.now().replace(day=15),
            season=season,
        )
        self.assertTrue(email_shows_partial_month([practice]))

    def test_mentor_pace_counts_from_rows_include_zero(self):
        rows = mentor_pace_counts_from_rows([], include_zero=True)
        self.assertEqual(len(rows), len(list(PaceTypes)))
        self.assertTrue(all(row["count"] == 0 for row in rows))

    def test_mentor_pace_counts_from_rows_excludes_zero_by_default(self):
        rows = mentor_pace_counts_from_rows(
            [{"pace": "8-9"}, {"pace": "8-9"}, {"pace": "not-a-pace"}]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], {"pace": "8-9", "count": 2})

    def test_email_response_pace_counts_skips_unknown_pace(self):
        class FakeToken:
            def __init__(self, mentor, id_):
                self.mentor = mentor
                self.id = id_

        class FakeMentor:
            def __init__(self, pace):
                self.pace = pace

        tokens = [FakeToken(FakeMentor("not-a-pace"), 1)]
        rows = email_response_pace_counts(tokens, set(), practice_id=1)
        totals = sum(row["emailed"] for row in rows)
        self.assertEqual(totals, 0)

    def test_build_practice_roster_report_empty_for_no_practices(self):
        self.assertEqual(build_practice_roster_report([]), [])

    def test_build_practice_roster_report_includes_coach_row(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=self.season,
        )
        coach = Coach.objects.create(
            first_name="Casey",
            last_name="Coach",
            email="casey@example.com",
        )
        coach.seasons.add(self.season)
        from tfk_mentors.models import CoachPracticeAssignment

        CoachPracticeAssignment.objects.create(
            coach=coach, practice=practice, pace="8-9"
        )
        report = build_practice_roster_report(
            Practice.objects.filter(pk=practice.pk)
        )
        self.assertEqual(len(report[0]["coaches"]), 1)
        self.assertEqual(report[0]["coaches"][0]["email"], "casey@example.com")

    def test_practice_mentor_result_payload_rejects_unexpected_type(self):
        with self.assertRaises(TypeError):
            practice_mentor_result_payload(object())

    def test_mentors_from_practice_replies_returns_latest_attending(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=self.season,
        )
        mentor_a = Mentor.objects.create(
            first_name="Amy",
            last_name="Alpha",
            email="amy-helper@example.com",
            type=MentorTypes.PRACTICE,
            pace="8-9",
        )
        mentor_b = Mentor.objects.create(
            first_name="Bo",
            last_name="Beta",
            email="bo-helper@example.com",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        # A non-attending reply from a third mentor exercises the "continue" branch
        # (reply.attendance not in attendance_values).
        mentor_c = Mentor.objects.create(
            first_name="Cara",
            last_name="Charlie",
            email="cara-helper@example.com",
            type=MentorTypes.PRACTICE,
            pace="8-9",
        )
        for mentor in (mentor_a, mentor_b, mentor_c):
            mentor.seasons.add(self.season)
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() + timedelta(days=1),
            body_text="Hi",
            recipient_season=self.season,
        )
        scheduled.practices.add(practice)
        scheduled.sync_mentor_tokens()
        for mentor in (mentor_a, mentor_b):
            token = ScheduledEmailMentorToken.objects.get(
                scheduled_email=scheduled, mentor=mentor
            )
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=token,
                mentor=mentor,
                practice=practice,
                attendance=PracticeAttendanceReply.ATTENDING,
                pace=mentor.pace,
            )
        token_c = ScheduledEmailMentorToken.objects.get(
            scheduled_email=scheduled, mentor=mentor_c
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token_c,
            mentor=mentor_c,
            practice=practice,
            attendance=PracticeAttendanceReply.NOT_ATTENDING,
        )
        # A second, older reply for mentor_a from a different scheduled email exercises
        # the "existing reply is already newer" branch (no replacement happens).
        scheduled_2 = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() + timedelta(days=1),
            body_text="Hi again",
            recipient_season=self.season,
        )
        scheduled_2.practices.add(practice)
        scheduled_2.sync_mentor_tokens()
        token_a_2 = ScheduledEmailMentorToken.objects.get(
            scheduled_email=scheduled_2, mentor=mentor_a
        )
        older_reply = ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token_a_2,
            mentor=mentor_a,
            practice=practice,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace=mentor_a.pace,
        )
        ScheduledEmailMentorPracticeReply.objects.filter(pk=older_reply.pk).update(
            updated_at=timezone.now() - timedelta(days=1)
        )
        latest = mentors_from_practice_replies(practice)
        self.assertEqual(len(latest), 2)
        self.assertNotIn(mentor_c, [reply.mentor for reply in latest])

    def test_email_shows_partial_month_false_for_full_span(self):
        import calendar
        from datetime import datetime
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("America/New_York")
        year, month = 2027, 6
        first_of_month = datetime(year, month, 1, 12, 0, tzinfo=tz)
        last_day = calendar.monthrange(year, month)[1]
        last_of_month = datetime(year, month, last_day, 12, 0, tzinfo=tz)
        practice_a = Practice.objects.create(date=first_of_month, season=self.season)
        practice_b = Practice.objects.create(date=last_of_month, season=self.season)
        self.assertFalse(email_shows_partial_month([practice_a, practice_b]))

    def test_validate_practice_attendance_split_practice_rejects_full_attending_choice(
        self,
    ):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=self.season,
            full_practice=False,
        )
        mentor = Mentor.objects.create(
            first_name="A",
            last_name="B",
            email="split-invalid@example.com",
            type=MentorTypes.PRACTICE,
            split_practice=True,
        )
        with self.assertRaises(ValueError):
            validate_practice_attendance(
                practice, mentor, PracticeAttendanceReply.ATTENDING
            )

    def test_validate_practice_attendance_non_split_accepts_attending(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=self.season,
            full_practice=False,
        )
        mentor = Mentor.objects.create(
            first_name="A",
            last_name="B",
            email="non-split-valid@example.com",
            type=MentorTypes.PRACTICE,
            split_practice=False,
        )
        validate_practice_attendance(
            practice, mentor, PracticeAttendanceReply.ATTENDING
        )

    def test_validate_practice_attendance_split_practice_accepts_first_half(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=self.season,
            full_practice=False,
        )
        mentor = Mentor.objects.create(
            first_name="A",
            last_name="B",
            email="split-valid@example.com",
            type=MentorTypes.PRACTICE,
            split_practice=True,
        )
        validate_practice_attendance(
            practice, mentor, PracticeAttendanceReply.FIRST_HALF
        )


class PracticeRosterReportEdgeTests(TestCase):
    def setUp(self):
        self.client = authed_client()
        self.season = Season.objects.create(year=2026)

    def test_invalid_season_returns_400(self):
        response = self.client.get("/api/reports/practice-roster/?season=abc")
        self.assertEqual(response.status_code, 400)

    def test_filters_by_valid_season(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=self.season,
        )
        other_season = Season.objects.create(year=2027)
        Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=other_season,
        )
        response = self.client.get(
            f"/api/reports/practice-roster/?season={self.season.id}"
        )
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.data}
        self.assertEqual(ids, {practice.id})


class MentorNonResponseReportEdgeTests(TestCase):
    def setUp(self):
        self.client = authed_client()
        self.season = Season.objects.create(year=2026)

    def test_invalid_season_returns_400(self):
        response = self.client.get("/api/reports/mentor-non-responses/?season=abc")
        self.assertEqual(response.status_code, 400)

    def test_no_practices_at_all_returns_empty_report(self):
        empty_season = Season.objects.create(year=2099)
        response = self.client.get(
            f"/api/reports/mentor-non-responses/?season={empty_season.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["practices"], [])
        self.assertEqual(response.data["summary"]["mentors_emailed"], 0)

    def test_practice_with_no_sent_email_reports_zero_counts(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=7),
            season=self.season,
        )
        response = self.client.get("/api/reports/mentor-non-responses/")
        self.assertEqual(response.status_code, 200)
        row = next(
            item for item in response.data["practices"] if item["id"] == practice.id
        )
        self.assertFalse(row["email_sent"])
        self.assertIsNone(row["scheduled_email_id"])
        self.assertTrue(
            all(pace_row["emailed"] == 0 for pace_row in row["response_pace_counts"])
        )

    def test_older_email_practice_overlap_does_not_override_latest(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=7),
            season=self.season,
        )
        newer = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() - timedelta(hours=1),
            task_completed_at=timezone.now() - timedelta(hours=1),
            body_text="Newer",
            recipient_season=self.season,
        )
        newer.practices.add(practice)
        older = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() - timedelta(days=2),
            task_completed_at=timezone.now() - timedelta(days=2),
            body_text="Older",
            recipient_season=self.season,
        )
        older.practices.add(practice)

        response = self.client.get("/api/reports/mentor-non-responses/")
        self.assertEqual(response.status_code, 200)
        row = next(
            item for item in response.data["practices"] if item["id"] == practice.id
        )
        self.assertEqual(row["scheduled_email_id"], newer.id)


class MentorScheduleViewErrorTests(TestCase):
    def setUp(self):
        self.client = authed_client()
        self.season = Season.objects.create(year=2026)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=7),
            season=self.season,
            full_practice=True,
        )

    def _url(self):
        return "/api/practices/schedule-mentors/"

    def test_missing_practice_ids_returns_400(self):
        response = self.client.post(self._url(), {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("non-empty list", response.data["detail"])

    def test_empty_practice_ids_returns_400(self):
        response = self.client.post(
            self._url(), {"practice_ids": []}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_non_integer_practice_ids_returns_400(self):
        response = self.client.post(
            self._url(), {"practice_ids": ["abc"]}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("must contain integers", response.data["detail"])

    def test_unknown_practice_id_returns_404(self):
        response = self.client.post(
            self._url(), {"practice_ids": [999999]}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_apply_with_invalid_schedule_shape_returns_400(self):
        response = self.client.post(
            self._url(),
            {
                "practice_ids": [self.practice.id],
                "apply": True,
                "schedule": {"practices": "not-a-list"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("must be a list", response.data["detail"])


class MentorScheduledEmailReplyEdgeTests(TestCase):
    def setUp(self):
        self.client = authed_client()
        self.season = Season.objects.create(year=2026)
        now = timezone.now()
        self.practices = [
            Practice.objects.create(
                date=now + timedelta(days=offset),
                season=self.season,
                full_practice=True,
            )
            for offset in (1, 2)
        ]
        self.mentor = Mentor.objects.create(
            first_name="Pat",
            last_name="Mentor",
            email="pat@example.com",
            cell_phone="555-0100",
            type=MentorTypes.PRACTICE,
            pace="11-12",
        )
        self.mentor.seasons.add(self.season)
        self.remote_mentor = Mentor.objects.create(
            first_name="Rem",
            last_name="Remote",
            email="remote@example.com",
            type=MentorTypes.REMOTE,
        )
        self.remote_mentor.seasons.add(self.season)
        self.scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=now + timedelta(days=7),
            body_text="Hello {{ first_name }}",
            recipient_season=self.season,
        )
        self.scheduled.practices.set(self.practices)
        self.scheduled.sync_mentor_tokens()
        self.token_row = ScheduledEmailMentorToken.objects.get(
            scheduled_email=self.scheduled,
            mentor=self.mentor,
        )
        self.remote_token_row = ScheduledEmailMentorToken.objects.get(
            scheduled_email=self.scheduled,
            mentor=self.remote_mentor,
        )

    def test_get_missing_token_returns_400(self):
        response = self.client.get("/api/mentor-email-reply/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing or invalid token", response.data["detail"])

    def test_get_invalid_token_format_returns_400(self):
        response = self.client.get("/api/mentor-email-reply/?token=not-a-uuid")
        self.assertEqual(response.status_code, 400)

    def test_get_unknown_token_returns_404(self):
        response = self.client.get(f"/api/mentor-email-reply/{uuid.uuid4()}/")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Invalid link", response.data["detail"])

    def test_put_unknown_token_returns_404(self):
        response = self.client.put(
            f"/api/mentor-email-reply/{uuid.uuid4()}/",
            {"replies": []},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("Invalid link", response.data["detail"])

    def _url(self, token=None):
        return f"/api/mentor-email-reply/{token or self.token_row.token}/"

    def test_put_replies_not_list_returns_400(self):
        response = self.client.put(
            self._url(), {"replies": "nope"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Expected 'replies' list", response.data["detail"])

    def test_put_remote_mentor_without_confirmation_returns_400(self):
        response = self.client.put(
            self._url(self.remote_token_row.token),
            {
                "mentor_pace": "10-11",
                "replies": [
                    {
                        "practice": p.id,
                        "attendance": PracticeAttendanceReply.ATTENDING,
                        "pace": "",
                    }
                    for p in self.practices
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("confirm", response.data["detail"].lower())

    def test_put_reply_item_not_object_returns_400(self):
        response = self.client.put(
            self._url(), {"replies": ["not-a-dict"]}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("must be an object", response.data["detail"])

    def test_put_invalid_practice_id_returns_400(self):
        response = self.client.put(
            self._url(),
            {
                "replies": [
                    {
                        "practice": "abc",
                        "attendance": PracticeAttendanceReply.ATTENDING,
                        "pace": "",
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid practice id", response.data["detail"])

    def test_put_duplicate_practice_returns_400(self):
        response = self.client.put(
            self._url(),
            {
                "replies": [
                    {
                        "practice": self.practices[0].id,
                        "attendance": PracticeAttendanceReply.ATTENDING,
                        "pace": "",
                    },
                    {
                        "practice": self.practices[0].id,
                        "attendance": PracticeAttendanceReply.NOT_ATTENDING,
                        "pace": "",
                    },
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Duplicate practice", response.data["detail"])

    def test_put_practice_not_in_email_returns_400(self):
        other_practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=30),
            season=self.season,
            full_practice=True,
        )
        response = self.client.put(
            self._url(),
            {
                "replies": [
                    {
                        "practice": other_practice.id,
                        "attendance": PracticeAttendanceReply.ATTENDING,
                        "pace": "",
                    }
                ]
                + [
                    {
                        "practice": p.id,
                        "attendance": PracticeAttendanceReply.NOT_ATTENDING,
                        "pace": "",
                    }
                    for p in self.practices
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not part of this email", response.data["detail"])

    def test_put_missing_reply_for_a_practice_returns_400(self):
        response = self.client.put(
            self._url(),
            {
                "replies": [
                    {
                        "practice": self.practices[0].id,
                        "attendance": PracticeAttendanceReply.ATTENDING,
                        "pace": "",
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("exactly one reply per practice", response.data["detail"])
        self.assertIn(self.practices[1].id, response.data["missing"])

    def test_put_remote_attending_without_mentor_pace_returns_400(self):
        response = self.client.put(
            self._url(self.remote_token_row.token),
            {
                "email_received_confirmed": True,
                "replies": [
                    {
                        "practice": p.id,
                        "attendance": PracticeAttendanceReply.ATTENDING,
                        "pace": "",
                    }
                    for p in self.practices
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Select your pace group", response.data["detail"])

    def test_put_remote_attending_with_invalid_mentor_pace_returns_400(self):
        response = self.client.put(
            self._url(self.remote_token_row.token),
            {
                "email_received_confirmed": True,
                "mentor_pace": "not-a-pace",
                "replies": [
                    {
                        "practice": p.id,
                        "attendance": PracticeAttendanceReply.ATTENDING,
                        "pace": "",
                    }
                    for p in self.practices
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid pace choice", response.data["detail"])

    def test_put_remote_not_attending_any_skips_pace_requirement(self):
        response = self.client.put(
            self._url(self.remote_token_row.token),
            {
                "email_received_confirmed": True,
                "replies": [
                    {
                        "practice": p.id,
                        "attendance": PracticeAttendanceReply.NOT_ATTENDING,
                        "pace": "",
                    }
                    for p in self.practices
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_put_invalid_attendance_choice_returns_400(self):
        response = self.client.put(
            self._url(),
            {
                "replies": [
                    {"practice": p.id, "attendance": "bogus-choice", "pace": ""}
                    for p in self.practices
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class ScheduledEmailViewSetEdgeTests(TestCase):
    def setUp(self):
        self.client = authed_client()
        self.season = Season.objects.create(year=2026)
        self.mentor = Mentor.objects.create(
            first_name="Pat",
            last_name="Mentor",
            email="pat@example.com",
            cell_phone="555-0100",
            type=MentorTypes.PRACTICE,
            pace="11-12",
        )
        self.mentor.seasons.add(self.season)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=7),
            season=self.season,
            full_practice=True,
        )
        self.scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() + timedelta(days=1),
            body_text="Hello",
            recipient_season=self.season,
        )

    def test_patch_unsent_email_syncs_mentor_tokens(self):
        response = self.client.patch(
            f"/api/scheduled-email/{self.scheduled.id}/",
            {"practices": [self.practice.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            ScheduledEmailMentorToken.objects.filter(
                scheduled_email=self.scheduled
            ).exists()
        )

    def test_patch_sent_email_does_not_resync_tokens(self):
        self.scheduled.task_completed_at = timezone.now()
        self.scheduled.save(update_fields=["task_completed_at"])
        response = self.client.patch(
            f"/api/scheduled-email/{self.scheduled.id}/",
            {"body_text": "Updated body"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            ScheduledEmailMentorToken.objects.filter(
                scheduled_email=self.scheduled
            ).exists()
        )

    def test_send_now_value_error_returns_400(self):
        with patch(
            "tfk_mentors.views.send_scheduled_email_now",
            side_effect=ValueError("no recipients"),
        ):
            response = self.client.post(
                f"/api/scheduled-email/{self.scheduled.id}/send-now/"
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("no recipients", response.data["detail"])

    def test_send_now_connection_error_returns_502(self):
        with patch(
            "tfk_mentors.views.send_scheduled_email_now",
            side_effect=ConnectionError("smtp down"),
        ):
            response = self.client.post(
                f"/api/scheduled-email/{self.scheduled.id}/send-now/"
            )
        self.assertEqual(response.status_code, 502)

    def test_pending_mentors_requires_sent_email(self):
        response = self.client.get(
            f"/api/scheduled-email/{self.scheduled.id}/pending-mentors/"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("only available after", response.data["detail"])

    def test_pending_mentors_falls_back_when_stats_missing_list(self):
        self.scheduled.task_completed_at = timezone.now()
        self.scheduled.save(update_fields=["task_completed_at"])
        with patch(
            "tfk_mentors.models.ScheduledEmail.reply_stats",
            return_value={"pending_mentor_ids": [], "pending_mentors": None},
        ):
            response = self.client.get(
                f"/api/scheduled-email/{self.scheduled.id}/pending-mentors/"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["pending_mentors"], [])

    def test_send_reply_reminders_value_error_returns_400(self):
        self.scheduled.task_completed_at = timezone.now()
        self.scheduled.save(update_fields=["task_completed_at"])
        with patch(
            "tfk_mentors.views.send_reply_reminders_for_email",
            side_effect=ValueError("boom"),
        ):
            response = self.client.post(
                f"/api/scheduled-email/{self.scheduled.id}/send-reply-reminders/"
            )
        self.assertEqual(response.status_code, 400)

    def test_send_reply_reminders_connection_error_returns_502(self):
        self.scheduled.task_completed_at = timezone.now()
        self.scheduled.save(update_fields=["task_completed_at"])
        with patch(
            "tfk_mentors.views.send_reply_reminders_for_email",
            side_effect=ConnectionError("smtp down"),
        ):
            response = self.client.post(
                f"/api/scheduled-email/{self.scheduled.id}/send-reply-reminders/"
            )
        self.assertEqual(response.status_code, 502)


class PracticeReminderEmailViewSetEdgeTests(TestCase):
    def setUp(self):
        self.client = authed_client()
        self.season = Season.objects.create(year=2026)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=7),
            season=self.season,
            full_practice=True,
        )
        sync_practice_reminders_for_season(self.season)
        self.reminder = PracticeReminderEmail.objects.filter(
            season=self.season
        ).first()

    def test_list_with_invalid_season_returns_empty(self):
        response = self.client.get(
            "/api/practice-reminder-email/?season=not-a-number"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_destroy_already_sent_reminder_returns_400(self):
        self.reminder.task_completed_at = timezone.now()
        self.reminder.save(update_fields=["task_completed_at"])
        response = self.client.delete(
            f"/api/practice-reminder-email/{self.reminder.id}/"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot be deleted", response.data["detail"])

    def test_sync_missing_season_returns_400(self):
        response = self.client.post(
            "/api/practice-reminder-email/sync/", {}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("season is required", response.data["detail"])

    def test_sync_unknown_season_returns_404(self):
        response = self.client.post(
            "/api/practice-reminder-email/sync/",
            {"season": 999999},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_refresh_templates_missing_season_returns_400(self):
        response = self.client.post(
            "/api/practice-reminder-email/refresh-templates/", {}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_refresh_templates_unknown_season_returns_404(self):
        response = self.client.post(
            "/api/practice-reminder-email/refresh-templates/",
            {"season": 999999},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_send_now_already_sent_returns_400(self):
        self.reminder.task_completed_at = timezone.now()
        self.reminder.save(update_fields=["task_completed_at"])
        response = self.client.post(
            f"/api/practice-reminder-email/{self.reminder.id}/send-now/"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("already been sent", response.data["detail"])

    def test_send_now_value_error_returns_400(self):
        with patch(
            "tfk_mentors.views.send_practice_reminder",
            side_effect=ValueError("no recipients"),
        ):
            response = self.client.post(
                f"/api/practice-reminder-email/{self.reminder.id}/send-now/"
            )
        self.assertEqual(response.status_code, 400)

    def test_send_now_connection_error_returns_502(self):
        with patch(
            "tfk_mentors.views.send_practice_reminder",
            side_effect=ConnectionError("smtp down"),
        ):
            response = self.client.post(
                f"/api/practice-reminder-email/{self.reminder.id}/send-now/"
            )
        self.assertEqual(response.status_code, 502)


class PracticeAttendanceEdgeTests(TestCase):
    def setUp(self):
        self.client = authed_client()
        self.season = Season.objects.create(year=2026)
        self.practice = Practice.objects.create(
            date=timezone.now() - timedelta(hours=1),
            season=self.season,
            full_practice=True,
        )
        self.mentor = Mentor.objects.create(
            first_name="Pat",
            last_name="Mentor",
            email="pat@example.com",
            cell_phone="555-0100",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.TEN.value,
        )
        self.mentor.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=self.mentor,
            practice=self.practice,
            pace=self.mentor.pace,
            is_available=False,
        )
        self.practice.mentors.add(self.mentor)

    def test_current_returns_none_when_no_practice(self):
        Practice.objects.all().delete()
        response = self.client.get("/api/practice-attendance/current/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["practice"])

    def test_archive_invalid_season_returns_400(self):
        response = self.client.get(
            "/api/practice-attendance/archived/?season=abc"
        )
        self.assertEqual(response.status_code, 400)

    def test_detail_get_missing_practice_returns_404(self):
        response = self.client.get("/api/practice-attendance/999999/")
        self.assertEqual(response.status_code, 404)

    def test_detail_patch_missing_practice_returns_404(self):
        response = self.client.patch(
            "/api/practice-attendance/999999/", {}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_patch_comments_none_clears_to_empty_string(self):
        self.practice.attendance_comments = "existing"
        self.practice.save(update_fields=["attendance_comments"])
        response = self.client.patch(
            f"/api/practice-attendance/{self.practice.id}/",
            {"attendance_comments": None},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.practice.refresh_from_db()
        self.assertEqual(self.practice.attendance_comments, "")

    def test_patch_without_mentors_key_skips_mentor_block(self):
        response = self.client.patch(
            f"/api/practice-attendance/{self.practice.id}/",
            {"attendance_comments": "just a note"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.practice.refresh_from_db()
        self.assertEqual(self.practice.attendance_comments, "just a note")

    def test_patch_mentors_not_a_list_returns_400(self):
        response = self.client.patch(
            f"/api/practice-attendance/{self.practice.id}/",
            {"mentors": {"mentor_id": self.mentor.id}},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("mentors must be a list", response.data["detail"])

    def test_patch_mentor_row_not_object_returns_400(self):
        response = self.client.patch(
            f"/api/practice-attendance/{self.practice.id}/",
            {"mentors": ["not-a-dict"]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("must be an object", response.data["detail"])

    def test_patch_invalid_mentor_id_returns_400(self):
        response = self.client.patch(
            f"/api/practice-attendance/{self.practice.id}/",
            {"mentors": [{"mentor_id": "abc", "show_up": ShowUpStatus.ATTENDED}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid mentor id", response.data["detail"])

    def test_patch_invalid_show_up_value_returns_400(self):
        response = self.client.patch(
            f"/api/practice-attendance/{self.practice.id}/",
            {"mentors": [{"mentor_id": self.mentor.id, "show_up": "bogus"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("attended, missed, or", response.data["detail"])

    def test_patch_found_replacement_required_for_off_roster_mentor(self):
        outsider = Mentor.objects.create(
            first_name="Out",
            last_name="Sider",
            email="outsider@example.com",
            cell_phone="555-0199",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        outsider.seasons.add(self.season)
        from tfk_mentors.models import MentorPracticeShowUp

        MentorPracticeShowUp.objects.create(
            mentor=outsider,
            practice=self.practice,
            show_up=ShowUpStatus.FOUND_REPLACEMENT,
        )
        response = self.client.patch(
            f"/api/practice-attendance/{self.practice.id}/",
            {"mentors": [{"mentor_id": outsider.id, "show_up": ShowUpStatus.ATTENDED}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Only found replacement", response.data["detail"])

    def test_patch_found_replacement_allowed_for_off_roster_mentor(self):
        outsider = Mentor.objects.create(
            first_name="Out",
            last_name="Sider2",
            email="outsider3@example.com",
            cell_phone="555-0197",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        outsider.seasons.add(self.season)
        from tfk_mentors.models import MentorPracticeShowUp

        MentorPracticeShowUp.objects.create(
            mentor=outsider,
            practice=self.practice,
            show_up=ShowUpStatus.FOUND_REPLACEMENT,
        )
        response = self.client.patch(
            f"/api/practice-attendance/{self.practice.id}/",
            {
                "mentors": [
                    {
                        "mentor_id": outsider.id,
                        "show_up": ShowUpStatus.FOUND_REPLACEMENT,
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        show_up = MentorPracticeShowUp.objects.get(
            mentor=outsider, practice=self.practice
        )
        self.assertEqual(show_up.show_up, ShowUpStatus.FOUND_REPLACEMENT)


class PublicDirectoryEdgeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.season = Season.objects.create(year=2026)

    def test_mentor_directory_practices_unknown_mentor_returns_404(self):
        response = self.client.get("/api/public/mentor-directory/999999/practices/")
        self.assertEqual(response.status_code, 404)

    def test_practice_mentor_roster_unknown_practice_returns_404(self):
        response = self.client.get("/api/public/practice/999999/mentors/")
        self.assertEqual(response.status_code, 404)

    def test_practice_mentor_roster_hidden_practice_returns_404(self):
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=self.season,
            show_to_mentors=False,
        )
        response = self.client.get(f"/api/public/practice/{practice.id}/mentors/")
        self.assertEqual(response.status_code, 404)


class MentorCellPhoneRequestListEdgeTests(TestCase):
    def setUp(self):
        self.client = authed_client()
        self.season = Season.objects.create(year=2026)

    def test_list_without_season_returns_all(self):
        response = self.client.get("/api/mentor-cell-phone-request/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["missing_mentors"], [])

    def test_list_invalid_season_returns_400(self):
        response = self.client.get("/api/mentor-cell-phone-request/?season=abc")
        self.assertEqual(response.status_code, 400)

    def test_list_unknown_season_returns_404(self):
        response = self.client.get("/api/mentor-cell-phone-request/?season=999999")
        self.assertEqual(response.status_code, 404)

    def test_send_without_season_uses_all_seasons(self):
        response = self.client.post(
            "/api/mentor-cell-phone-request/send/", {}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_send_invalid_season_returns_400(self):
        response = self.client.post(
            "/api/mentor-cell-phone-request/send/",
            {"season": "abc"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class MentorCellPhoneUpdateEdgeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.mentor = Mentor.objects.create(
            first_name="No",
            last_name="Phone",
            email="nophone@example.com",
            cell_phone="",
            type=MentorTypes.REMOTE,
            pace=PaceTypes.TEN.value,
        )
        self.send_batch = MentorCellPhoneRequestSend.objects.create(
            sent_at=timezone.now(),
            recipients_emailed_count=1,
        )
        self.token_row = MentorCellPhoneRequestToken.objects.create(
            send=self.send_batch,
            mentor=self.mentor,
            sent_at=timezone.now(),
        )

    def test_get_missing_token_returns_400(self):
        response = self.client.get("/api/mentor-cell-phone-update/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Token is required", response.data["detail"])

    def test_get_invalid_token_format_returns_400(self):
        response = self.client.get(
            "/api/mentor-cell-phone-update/?token=not-a-uuid"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid token", response.data["detail"])

    def test_get_unknown_token_returns_404(self):
        response = self.client.get(
            f"/api/mentor-cell-phone-update/{uuid.uuid4()}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_get_when_mentor_already_has_phone_returns_410(self):
        self.mentor.cell_phone = "555-9999"
        self.mentor.save(update_fields=["cell_phone"])
        response = self.client.get(
            f"/api/mentor-cell-phone-update/{self.token_row.token}/"
        )
        self.assertEqual(response.status_code, 410)
        self.assertTrue(response.data["already_complete"])

    def test_put_missing_token_returns_400(self):
        response = self.client.put(
            "/api/mentor-cell-phone-update/", {"cell_phone": "555-1111"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Token is required", response.data["detail"])

    def test_put_invalid_token_format_returns_400(self):
        response = self.client.put(
            "/api/mentor-cell-phone-update/",
            {"token": "not-a-uuid", "cell_phone": "555-1111"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_put_unknown_token_returns_404(self):
        response = self.client.put(
            f"/api/mentor-cell-phone-update/{uuid.uuid4()}/",
            {"cell_phone": "555-1111"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_put_empty_cell_phone_returns_400(self):
        response = self.client.put(
            f"/api/mentor-cell-phone-update/{self.token_row.token}/",
            {"cell_phone": "  "},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("enter your cell phone", response.data["detail"])

    def test_put_cell_phone_too_long_returns_400(self):
        response = self.client.put(
            f"/api/mentor-cell-phone-update/{self.token_row.token}/",
            {"cell_phone": "1" * 21},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("20 characters or fewer", response.data["detail"])

    def test_put_locked_row_missing_returns_410(self):
        with patch.object(
            MentorCellPhoneRequestToken.objects, "select_for_update"
        ) as mock_lock:
            chain = MagicMock()
            chain.select_related.return_value.filter.return_value.first.return_value = None
            mock_lock.return_value = chain
            response = self.client.put(
                f"/api/mentor-cell-phone-update/{self.token_row.token}/",
                {"cell_phone": "555-1111"},
                format="json",
            )
        self.assertEqual(response.status_code, 410)
