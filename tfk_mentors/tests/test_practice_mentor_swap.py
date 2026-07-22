from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tfk_mentors.models import (
    Coach,
    Mentor,
    MentorPracticeAssignment,
    MentorPracticeShowUp,
    MentorTypes,
    PaceTypes,
    Practice,
    PracticeReminderEmail,
    PracticeReminderKind,
    Season,
    ShowUpStatus,
)
from tfk_mentors.practice_reminder import sync_practice_reminders_for_season


class PracticeMentorSwapTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()

        self._email_patcher = patch(
            "tfk_mentors.practice_swap_notification._verify_email_delivery"
        )
        self._email_patcher.start()
        self.addCleanup(self._email_patcher.stop)

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

    def test_swap_replaces_mentor_and_records_found_replacement(self):
        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["outgoing_mentor_id"], self.outgoing.id)
        self.assertEqual(response.data["show_up"], ShowUpStatus.FOUND_REPLACEMENT)
        self.assertIsNone(response.data["coach_notification"])
        self.assertEqual(response.data["mentor_confirmations"]["sent"], 2)

        self.practice.refresh_from_db()
        self.assertNotIn(self.outgoing, self.practice.mentors.all())
        self.assertIn(self.incoming, self.practice.mentors.all())
        show_up = MentorPracticeShowUp.objects.get(
            mentor=self.outgoing,
            practice=self.practice,
        )
        self.assertEqual(show_up.show_up, ShowUpStatus.FOUND_REPLACEMENT)

    def test_swap_sends_confirmation_emails_to_both_mentors(self):
        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)
        recipients = {tuple(message.to) for message in mail.outbox}
        self.assertEqual(
            recipients,
            {(self.outgoing.email,), (self.incoming.email,)},
        )
        for message in mail.outbox:
            self.assertEqual(message.subject, "TFK Mentor Swap Confirmation")
            self.assertIn(
                "Out Going has been replaced with In Coming",
                message.body,
            )
            self.assertIn(
                "If this was made in error please reply to this email.",
                message.body,
            )

    def test_attendance_payload_includes_swapped_out_mentor(self):
        self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        response = self.client.get(f"/api/practice-attendance/{self.practice.id}/")
        self.assertEqual(response.status_code, 200)
        mentors = response.data["assigned_mentors"]
        swapped = next(
            row for row in mentors if row["mentor_id"] == self.outgoing.id
        )
        self.assertTrue(swapped["swapped_out"])
        self.assertEqual(swapped["show_up"], ShowUpStatus.FOUND_REPLACEMENT)

    def test_archived_attendance_counts_found_replacement(self):
        self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.practice.date = timezone.now() - timedelta(days=2)
        self.practice.save(update_fields=["date", "updated_at"])

        response = self.client.get("/api/practice-attendance/archived/")
        self.assertEqual(response.status_code, 200)
        row = next(
            item for item in response.data if item["practice_id"] == self.practice.id
        )
        self.assertEqual(row["found_replacement_count"], 1)
        self.assertEqual(row["assigned_count"], 1)

    def test_swap_rejects_incoming_mentor_already_on_practice(self):
        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.outgoing.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_swap_allows_incoming_mentor_marked_available(self):
        available = Mentor.objects.create(
            first_name="Avail",
            last_name="Able",
            email="avail@example.com",
            cell_phone="555-0102",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        available.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=available,
            practice=self.practice,
            pace=available.pace,
            is_available=True,
        )

        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": available.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["incoming_mentor"]["mentor_id"], available.id)

        self.practice.refresh_from_db()
        self.assertNotIn(self.outgoing, self.practice.mentors.all())
        self.assertIn(available, self.practice.mentors.all())
        self.assertFalse(
            MentorPracticeAssignment.objects.filter(
                mentor=available,
                practice=self.practice,
                is_available=True,
            ).exists()
        )

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

    def test_swap_emails_coaches_after_last_reminder_sent(self):
        coach = Coach.objects.create(
            first_name="Casey",
            last_name="Coach",
            email="casey@example.com",
            cell="555-0200",
        )
        coach.seasons.add(self.season)

        head_coach = Coach.objects.create(
            first_name="Head",
            last_name="Coach",
            email="head@example.com",
        )
        head_coach.seasons.add(self.season)
        self.season.head_coach = head_coach
        self.season.save(update_fields=["head_coach"])

        other_coach = Coach.objects.create(
            first_name="Other",
            last_name="Season",
            email="other@example.com",
        )
        other_coach.seasons.add(self.season)

        outside = Coach.objects.create(
            first_name="Out",
            last_name="Side",
            email="outside@example.com",
        )
        outside_season = Season.objects.create(year=2025)
        outside.seasons.add(outside_season)

        self._mark_last_reminder_sent(self.practice)

        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["mentor_confirmations"]["sent"], 2)
        self.assertEqual(response.data["coach_notification"]["sent"], 1)
        self.assertEqual(response.data["coach_notification"]["recipients"], 3)
        self.assertEqual(len(mail.outbox), 3)

        mentor_messages = [
            message
            for message in mail.outbox
            if message.subject == "TFK Mentor Swap Confirmation"
        ]
        coach_messages = [
            message
            for message in mail.outbox
            if message.subject.startswith("Mentor swap for TFK practice")
        ]
        self.assertEqual(len(mentor_messages), 2)
        self.assertEqual(len(coach_messages), 1)
        self.assertCountEqual(
            coach_messages[0].to,
            [coach.email, head_coach.email, other_coach.email],
        )
        self.assertNotIn(outside.email, coach_messages[0].to)
        self.assertIn("In Coming is replacing Out Going", coach_messages[0].body)
        self.assertIn(PaceTypes.TEN.value, coach_messages[0].body)
        self.assertIn("555-0101", coach_messages[0].body)

    def test_swap_does_not_duplicate_head_coach_also_in_season(self):
        head_coach = Coach.objects.create(
            first_name="Head",
            last_name="Coach",
            email="head@example.com",
        )
        head_coach.seasons.add(self.season)
        self.season.head_coach = head_coach
        self.season.save(update_fields=["head_coach"])
        self._mark_last_reminder_sent(self.practice)

        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["coach_notification"]["sent"], 1)
        self.assertEqual(response.data["coach_notification"]["recipients"], 1)
        coach_messages = [
            message
            for message in mail.outbox
            if message.subject.startswith("Mentor swap for TFK practice")
        ]
        self.assertEqual(len(coach_messages), 1)
        self.assertEqual(coach_messages[0].to, [head_coach.email])

    def test_swap_skips_coach_email_when_reminder_not_sent(self):
        coach = Coach.objects.create(
            first_name="Casey",
            last_name="Coach",
            email="casey@example.com",
        )
        coach.seasons.add(self.season)

        Practice.objects.create(
            date=self.practice.date - timedelta(days=7),
            season=self.season,
            full_practice=True,
        )
        sync_practice_reminders_for_season(self.season)
        reminder = PracticeReminderEmail.objects.get(practice_one=self.practice)
        self.assertIsNone(reminder.task_completed_at)

        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["coach_notification"])
        self.assertEqual(response.data["mentor_confirmations"]["sent"], 2)
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(
            all(
                message.subject == "TFK Mentor Swap Confirmation"
                for message in mail.outbox
            )
        )

    def test_swap_skips_all_emails_after_practice_has_started(self):
        coach = Coach.objects.create(
            first_name="Casey",
            last_name="Coach",
            email="casey@example.com",
        )
        coach.seasons.add(self.season)
        self.season.head_coach = coach
        self.season.save(update_fields=["head_coach"])

        self._mark_last_reminder_sent(self.practice)
        self.practice.date = timezone.now() - timedelta(minutes=5)
        self.practice.save(update_fields=["date", "updated_at"])

        response = self.client.post(
            f"/api/practice/{self.practice.id}/swap-mentor/",
            {
                "outgoing_mentor": self.outgoing.id,
                "incoming_mentor": self.incoming.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["mentor_confirmations"])
        self.assertIsNone(response.data["coach_notification"])
        self.assertEqual(len(mail.outbox), 0)
