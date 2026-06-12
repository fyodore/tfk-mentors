import io

from django.test import TestCase
from rest_framework.test import APIClient

from tfk_mentors.models import Mentor, Season, normalize_pace


class NormalizePaceTests(TestCase):
    def test_collapses_double_dash(self):
        self.assertEqual(normalize_pace("8--9"), "8-9")

    def test_strips_spaces_and_unicode_dashes(self):
        self.assertEqual(normalize_pace("8 – 9"), "8-9")
        self.assertEqual(normalize_pace("10 - 11"), "10-11")

    def test_thirteen_plus_variants(self):
        self.assertEqual(normalize_pace("13+"), "13+")
        self.assertEqual(normalize_pace("13-+"), "13+")
        self.assertEqual(normalize_pace("13 ++"), "13+")

    def test_valid_values_unchanged(self):
        for value in ("8-9", "9-10", "10-11", "11-12", "12-13", "13+"):
            self.assertEqual(normalize_pace(value), value)


class MentorCsvImportTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()
        self.season = Season.objects.create(year=2026)

    def _import_csv(self, body):
        upload = io.BytesIO(body.encode("utf-8"))
        upload.name = "mentors.csv"
        return self.client.post(
            "/api/mentor/import-csv/",
            {"file": upload},
            format="multipart",
        )

    def test_import_normalizes_double_dash_pace(self):
        csv_body = (
            "email,season_year,first_name,last_name,cell_phone,type,pace\n"
            "runner@example.com,2026,Jane,Doe,5551234567,At Practice,8--9\n"
        )
        response = self._import_csv(csv_body)
        self.assertEqual(response.status_code, 200)
        mentor = Mentor.objects.get(email="runner@example.com")
        self.assertEqual(mentor.pace, "8-9")

    def test_import_updates_existing_mentor_double_dash_pace(self):
        mentor = Mentor.objects.create(
            first_name="Jane",
            last_name="Doe",
            email="runner@example.com",
            cell_phone="5551234567",
            type="At Practice",
            pace="9-10",
        )
        mentor.seasons.add(self.season)
        csv_body = (
            "email,season_year,first_name,last_name,cell_phone,type,pace\n"
            "runner@example.com,2026,Jane,Doe,5551234567,At Practice,8--9\n"
        )
        response = self._import_csv(csv_body)
        self.assertEqual(response.status_code, 200)
        mentor.refresh_from_db()
        self.assertEqual(mentor.pace, "8-9")

    def test_model_save_normalizes_double_dash_pace(self):
        mentor = Mentor(
            first_name="Jane",
            last_name="Doe",
            email="runner@example.com",
            cell_phone="5551234567",
            type="At Practice",
            pace="8--9",
        )
        mentor.save()
        self.assertEqual(mentor.pace, "8-9")

    def test_import_reports_invalid_pace(self):
        csv_body = (
            "email,season_year,first_name,last_name,cell_phone,type,pace\n"
            "runner@example.com,2026,Jane,Doe,5551234567,At Practice,fast\n"
        )
        response = self._import_csv(csv_body)
        self.assertEqual(response.status_code, 207)
        self.assertFalse(Mentor.objects.filter(email="runner@example.com").exists())
        self.assertTrue(any("invalid pace" in err for err in response.data["errors"]))

    def test_import_allows_remote_without_pace(self):
        csv_body = (
            "email,season_year,first_name,last_name,cell_phone,type,pace\n"
            "remote@example.com,2026,Pat,Lee,5551234567,Remote,\n"
        )
        response = self._import_csv(csv_body)
        self.assertEqual(response.status_code, 200)
        mentor = Mentor.objects.get(email="remote@example.com")
        self.assertEqual(mentor.type, "Remote")
        self.assertEqual(mentor.pace, "")

    def test_import_requires_pace_for_at_practice(self):
        csv_body = (
            "email,season_year,first_name,last_name,cell_phone,type,pace\n"
            "runner@example.com,2026,Jane,Doe,5551234567,At Practice,\n"
        )
        response = self._import_csv(csv_body)
        self.assertEqual(response.status_code, 207)
        self.assertFalse(Mentor.objects.filter(email="runner@example.com").exists())
        self.assertTrue(
            any("pace is required" in err for err in response.data["errors"])
        )

    def test_api_create_remote_without_pace(self):
        response = self.client.post(
            "/api/mentor/",
            {
                "first_name": "Pat",
                "last_name": "Remote",
                "email": "remote-api@example.com",
                "cell_phone": "555-0100",
                "type": "Remote",
                "pace": "",
                "seasons": [self.season.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["pace"], "")
