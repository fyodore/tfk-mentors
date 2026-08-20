"""Coverage for serializers.py branches not exercised by feature tests."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import (
    Coach,
    CoachPracticeAssignment,
    Mentor,
    MentorPracticeAssignment,
    MentorTypes,
    PaceTypes,
    Practice,
    PracticeAttendanceReply,
    PracticeReminderEmail,
    PracticeReminderKind,
    ScheduledEmail,
    ScheduledEmailMentorPracticeReply,
    ScheduledEmailMentorToken,
    ScheduledEmailRecipientMode,
    Season,
)
from tfk_mentors.serializers import (
    PracticeReminderEmailListSerializer,
    ScheduledEmailListSerializer,
    ScheduledEmailSerializer,
    build_mentor_practice_rows,
    build_practice_attendance_payload,
    mentor_status_for_practice,
    practice_available_mentor_payloads,
)


class SeasonSerializerHeadCoachTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

    def test_patch_head_coach_to_null(self):
        season = Season.objects.create(year=2200)
        coach = Coach.objects.create(
            first_name="Head", last_name="Coach", email="headnull@example.com"
        )
        coach.seasons.add(season)
        season.head_coach = coach
        season.save(update_fields=["head_coach"])

        response = self.client.patch(
            f"/api/season/{season.id}/", {"head_coach": None}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["head_coach"])

    def test_create_season_with_head_coach_skips_membership_check(self):
        coach = Coach.objects.create(
            first_name="New", last_name="Coach", email="newcoach_ser@example.com"
        )
        response = self.client.post(
            "/api/season/",
            {"year": 2201, "head_coach": coach.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["head_coach"], coach.id)

    def test_create_season_marked_current_clears_other_current_season(self):
        other = Season.objects.create(year=2202, is_current=True)
        response = self.client.post(
            "/api/season/", {"year": 2203, "is_current": True}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        other.refresh_from_db()
        self.assertFalse(other.is_current)


class MentorSerializerValidationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

    def test_rejects_invalid_pace_choice(self):
        response = self.client.post(
            "/api/mentor/",
            {
                "first_name": "Bad",
                "last_name": "Pace",
                "email": "badpaceapi@example.com",
                "cell_phone": "555-0001",
                "type": MentorTypes.PRACTICE,
                "pace": "not-a-pace",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("pace", response.data)

    def test_requires_pace_for_at_practice_mentor(self):
        response = self.client.post(
            "/api/mentor/",
            {
                "first_name": "No",
                "last_name": "Pace",
                "email": "nopaceapi@example.com",
                "cell_phone": "555-0002",
                "type": MentorTypes.PRACTICE,
                "pace": "",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("pace", response.data)

    def test_requires_cell_phone_for_at_practice_mentor(self):
        response = self.client.post(
            "/api/mentor/",
            {
                "first_name": "No",
                "last_name": "Cell",
                "email": "nocellapi@example.com",
                "cell_phone": "",
                "type": MentorTypes.PRACTICE,
                "pace": PaceTypes.NINE.value,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("cell_phone", response.data)

    def test_creates_at_practice_mentor_with_valid_data(self):
        response = self.client.post(
            "/api/mentor/",
            {
                "first_name": "Valid",
                "last_name": "Mentor",
                "email": "validmentorapi@example.com",
                "cell_phone": "555-0003",
                "type": MentorTypes.PRACTICE,
                "pace": PaceTypes.NINE.value,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["pace"], PaceTypes.NINE.value)

    def test_creates_remote_mentor_without_pace_or_cell_phone(self):
        response = self.client.post(
            "/api/mentor/",
            {
                "first_name": "Remote",
                "last_name": "Mentor",
                "email": "remotementorapi@example.com",
                "type": MentorTypes.REMOTE,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["pace"], "")


class CoachPracticeAssignmentSerializerTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()
        self.season = Season.objects.create(year=2204)
        self.coach = Coach.objects.create(
            first_name="Cara", last_name="Coach", email="cpaser@example.com"
        )
        self.coach.seasons.add(self.season)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=self.season
        )

    def test_rejects_invalid_pace_choice(self):
        response = self.client.post(
            "/api/coach-practice-assignment/",
            {
                "coach": self.coach.id,
                "practice": self.practice.id,
                "pace": "bogus",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("pace", response.data)

    def test_accepts_and_normalizes_valid_pace_choice(self):
        response = self.client.post(
            "/api/coach-practice-assignment/",
            {
                "coach": self.coach.id,
                "practice": self.practice.id,
                "pace": "9--10",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["pace"], "9-10")


class PracticeAvailableMentorPayloadDedupTests(TestCase):
    def test_direct_assignment_deduped_when_mentor_already_available_via_reply(self):
        season = Season.objects.create(year=2205)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=season
        )
        mentor = Mentor.objects.create(
            first_name="Dedup",
            last_name="Available",
            email="dedupavailable@example.com",
            cell_phone="555-0004",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        mentor.seasons.add(season)
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_season=season,
        )
        scheduled.practices.add(practice)
        scheduled.sync_mentor_tokens()
        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=scheduled, mentor=mentor
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token,
            mentor=mentor,
            practice=practice,
            attendance=PracticeAttendanceReply.AVAILABLE,
            pace="9-10",
        )
        # Stale/duplicate direct assignment marking the same mentor available.
        MentorPracticeAssignment.objects.create(
            mentor=mentor, practice=practice, pace="9-10", is_available=True
        )
        payloads = practice_available_mentor_payloads(practice)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["mentor_id"], mentor.id)


class MentorStatusForPracticeAvailableLoopTests(TestCase):
    def test_skips_non_matching_replies_before_match(self):
        season = Season.objects.create(year=2206)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=season
        )
        first_mentor = Mentor.objects.create(
            first_name="First",
            last_name="Avail",
            email="firstavail@example.com",
            cell_phone="555-0005",
            type=MentorTypes.PRACTICE,
            pace="8-9",
        )
        second_mentor = Mentor.objects.create(
            first_name="Second",
            last_name="Avail",
            email="secondavail@example.com",
            cell_phone="555-0006",
            type=MentorTypes.PRACTICE,
            pace="12-13",
        )
        for mentor in (first_mentor, second_mentor):
            mentor.seasons.add(season)
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_season=season,
        )
        scheduled.practices.add(practice)
        scheduled.sync_mentor_tokens()
        for mentor, pace in ((first_mentor, "8-9"), (second_mentor, "12-13")):
            token = ScheduledEmailMentorToken.objects.get(
                scheduled_email=scheduled, mentor=mentor
            )
            ScheduledEmailMentorPracticeReply.objects.create(
                mentor_token=token,
                mentor=mentor,
                practice=practice,
                attendance=PracticeAttendanceReply.AVAILABLE,
                pace=pace,
            )
        # first_mentor sorts before second_mentor (lower pace), so checking
        # second_mentor's status requires skipping past first_mentor's reply.
        result = mentor_status_for_practice(second_mentor, practice)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["pace"], "12-13")


class BuildMentorPracticeRowsNoSeasonsTests(TestCase):
    def test_returns_empty_list_when_mentor_has_no_seasons(self):
        mentor = Mentor.objects.create(
            first_name="No",
            last_name="Seasons",
            email="noseasons@example.com",
            type=MentorTypes.REMOTE,
        )
        self.assertEqual(build_mentor_practice_rows(mentor), [])


class BuildPracticeAttendancePayloadExplicitNowTests(TestCase):
    def test_uses_provided_now_instead_of_computing_it(self):
        season = Season.objects.create(year=2213)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=season
        )
        fixed_now = timezone.now() - timedelta(days=100)
        payload = build_practice_attendance_payload(practice, now=fixed_now)
        self.assertEqual(payload["practice_id"], practice.id)


class PublicMentorDirectoryEdgeCaseTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_empty_directory_when_no_mentors_exist(self):
        response = self.client.get("/api/public/mentor-directory/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_stale_available_assignment_ignored_when_latest_reply_disagrees(self):
        season = Season.objects.create(year=2207)
        mentor = Mentor.objects.create(
            first_name="Stale",
            last_name="Assignment",
            email="staleassignment@example.com",
            cell_phone="555-0007",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        mentor.seasons.add(season)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1),
            season=season,
            show_to_mentors=True,
        )
        MentorPracticeAssignment.objects.create(
            mentor=mentor, practice=practice, pace="9-10", is_available=True
        )
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_season=season,
        )
        scheduled.practices.add(practice)
        scheduled.sync_mentor_tokens()
        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=scheduled, mentor=mentor
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token,
            mentor=mentor,
            practice=practice,
            attendance=PracticeAttendanceReply.NOT_ATTENDING,
            pace="9-10",
        )

        response = self.client.get("/api/public/mentor-directory/")
        row = next(item for item in response.data if item["id"] == mentor.id)
        self.assertEqual(row["assigned_count"], 0)
        self.assertEqual(row["available_count"], 0)



class ScheduledEmailSerializerValidateTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()
        self.season = Season.objects.create(year=2208)
        self.mentor = Mentor.objects.create(
            first_name="Specific",
            last_name="Target",
            email="specifictarget@example.com",
            cell_phone="555-0008",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        self.mentor.seasons.add(self.season)
        self.email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() + timedelta(days=1),
            body_text="Hello",
            recipient_season=self.season,
        )

    def test_create_with_specific_mentors_succeeds(self):
        response = self.client.post(
            "/api/scheduled-email/",
            {
                "scheduled_send_at": (timezone.now() + timedelta(days=2)).isoformat(),
                "body_text": "Hi {{ first_name }}",
                "recipient_mode": ScheduledEmailRecipientMode.SPECIFIC_MENTORS,
                "specific_mentors": [self.mentor.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["specific_mentors"], [self.mentor.id])
        self.assertIsNone(response.data["recipient_season"])

    def test_create_with_specific_mentors_requires_at_least_one(self):
        response = self.client.post(
            "/api/scheduled-email/",
            {
                "scheduled_send_at": (timezone.now() + timedelta(days=2)).isoformat(),
                "body_text": "Hi",
                "recipient_mode": ScheduledEmailRecipientMode.SPECIFIC_MENTORS,
                "specific_mentors": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("specific_mentors", response.data)

    def test_patch_without_recipient_fields_skips_recipient_validation(self):
        response = self.client.patch(
            f"/api/scheduled-email/{self.email.id}/",
            {"body_text": "Updated body only"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["body_text"], "Updated body only")

    def test_patch_recipient_mode_only_falls_back_to_existing_season_and_mentors(self):
        response = self.client.patch(
            f"/api/scheduled-email/{self.email.id}/",
            {"recipient_mode": ScheduledEmailRecipientMode.ALL_AT_PRACTICE_IN_SEASON},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["recipient_season"], self.season.id)

    def test_patch_all_in_season_with_null_season_rejected(self):
        response = self.client.patch(
            f"/api/scheduled-email/{self.email.id}/",
            {
                "recipient_mode": ScheduledEmailRecipientMode.ALL_IN_SEASON,
                "recipient_season": None,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("recipient_season", response.data)


class ScheduledEmailSerializerPendingMentorsFallbackTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2209)
        self.mentor = Mentor.objects.create(
            first_name="Fallback",
            last_name="Pending",
            email="fallbackpending@example.com",
            type=MentorTypes.REMOTE,
        )
        self.email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now() - timedelta(days=1),
            body_text="Hi",
            recipient_season=self.season,
            task_completed_at=timezone.now(),
        )

    def test_builds_rows_from_pending_mentor_ids_when_not_prebuilt(self):
        serializer = ScheduledEmailSerializer(self.email, context={})
        with patch.object(
            ScheduledEmailSerializer,
            "_sent_email_stats",
            return_value={"pending_mentor_ids": [self.mentor.id]},
        ):
            result = serializer.get_pending_mentors(self.email)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], self.mentor.id)

    def test_returns_empty_list_when_no_pending_ids(self):
        serializer = ScheduledEmailSerializer(self.email, context={})
        with patch.object(
            ScheduledEmailSerializer,
            "_sent_email_stats",
            return_value={"pending_mentor_ids": []},
        ):
            result = serializer.get_pending_mentors(self.email)
        self.assertEqual(result, [])


class ScheduledEmailListSerializerDirectTests(TestCase):
    def test_get_reply_stats_computes_when_not_prebuilt_in_context(self):
        season = Season.objects.create(year=2210)
        email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="Hi",
            recipient_season=season,
        )
        serializer = ScheduledEmailListSerializer(email, context={})
        stats = serializer.data["reply_stats"]
        self.assertIn("mentors_emailed", stats)


class PracticeReminderEmailValidateTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()
        self.season = Season.objects.create(year=2211)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=self.season
        )
        self.reminder = PracticeReminderEmail.objects.create(
            season=self.season,
            kind=PracticeReminderKind.AFTER_PRACTICE,
            anchor_practice=self.practice,
            practice_one=self.practice,
            subject="Subject",
            body_text="Body",
            task_completed_at=timezone.now(),
        )

    def test_cannot_patch_sent_reminder(self):
        response = self.client.patch(
            f"/api/practice-reminder-email/{self.reminder.id}/",
            {"subject": "New subject"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot be edited", str(response.data))


class PracticeReminderEmailListSerializerDirectTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2212)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=self.season
        )

    def test_recipient_count_uses_emailed_count_when_sent(self):
        reminder = PracticeReminderEmail.objects.create(
            season=self.season,
            kind=PracticeReminderKind.AFTER_PRACTICE,
            anchor_practice=self.practice,
            practice_one=self.practice,
            subject="Subject",
            body_text="Body",
            task_completed_at=timezone.now(),
            recipients_emailed_count=5,
        )
        serializer = PracticeReminderEmailListSerializer(reminder, context={})
        self.assertEqual(serializer.data["recipient_count"], 5)

    def test_recipient_count_falls_back_to_pending_lookup_when_uncached(self):
        reminder = PracticeReminderEmail.objects.create(
            season=self.season,
            kind=PracticeReminderKind.BEFORE_FIRST,
            anchor_practice=self.practice,
            practice_one=self.practice,
            subject="Subject",
            body_text="Body",
        )
        serializer = PracticeReminderEmailListSerializer(reminder, context={})
        # No "reminder_recipient_counts" in context: falls back to a direct
        # pending_recipients_for_reminder() lookup.
        self.assertIsInstance(serializer.data["recipient_count"], int)
