"""Lightweight coverage for __str__/getter/setter lines and small business
methods across models.py that aren't already exercised by feature tests."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from tfk_mentors.models import (
    Coach,
    CoachPracticeAssignment,
    Mentor,
    MentorAnswers,
    MentorCellPhoneRequestSend,
    MentorCellPhoneRequestToken,
    MentorPracticeAssignment,
    MentorPracticeShowUp,
    MentorSwapRequest,
    MentorSwapRequestStatus,
    MentorTypes,
    PaceTypes,
    Practice,
    PracticeAttendanceReply,
    PracticeReminderEmail,
    PracticeReminderKind,
    PracticeReminderSendRecord,
    PracticeReminderRecipientKind,
    PracticeReminderSuppression,
    Requests,
    RequestsSentLog,
    ScheduledEmail,
    ScheduledEmailMentorPracticeReply,
    ScheduledEmailMentorToken,
    Season,
    ShowUpStatus,
    TfkStaff,
    UnderfilledPaceMentorEmailSend,
    UnderfilledPaceMentorEmailToken,
    normalize_pace,
)


class NormalizePaceTests(TestCase):
    def test_none_returns_empty_string(self):
        self.assertEqual(normalize_pace(None), "")

    def test_blank_returns_empty_string(self):
        self.assertEqual(normalize_pace("   "), "")

    def test_collapses_whitespace(self):
        self.assertEqual(normalize_pace(" 8 - 9 "), "8-9")

    def test_normalizes_unicode_dash_variants(self):
        # en dash, em dash, minus sign, non-breaking hyphen
        self.assertEqual(normalize_pace("8\u20139"), "8-9")
        self.assertEqual(normalize_pace("8\u20149"), "8-9")
        self.assertEqual(normalize_pace("8\u22129"), "8-9")

    def test_collapses_repeated_dashes(self):
        self.assertEqual(normalize_pace("8--9"), "8-9")

    def test_collapses_repeated_plus_signs(self):
        self.assertEqual(normalize_pace("13++"), "13+")

    def test_thirteen_plus_normalizes_to_canonical_value(self):
        self.assertEqual(normalize_pace("13+"), PaceTypes.THIRTEEN.value)
        self.assertEqual(normalize_pace("13-14"), PaceTypes.THIRTEEN.value)

    def test_non_string_input_is_stringified(self):
        self.assertEqual(normalize_pace(13), PaceTypes.THIRTEEN.value)


class SeasonModelTests(TestCase):
    def test_str_is_year(self):
        season = Season.objects.create(year=2027)
        self.assertEqual(str(season), "2027")

    def test_getters_and_setters(self):
        coach = Coach.objects.create(
            first_name="Head", last_name="Coach", email="head@example.com"
        )
        season = Season.objects.create(year=2028)
        season.set_year(2029)
        season.set_head_coach(coach)
        self.assertEqual(season.get_year(), 2029)
        self.assertEqual(season.get_head_coach(), coach)

    def test_created_updated_at_getters_setters(self):
        season = Season.objects.create(year=2030)
        now = timezone.now()
        season.set_created_at(now)
        season.set_updated_at(now)
        self.assertEqual(season.get_created_at(), now)
        self.assertEqual(season.get_updated_at(), now)


class CoachModelTests(TestCase):
    def test_str_and_getters_setters(self):
        coach = Coach()
        coach.set_first_name("Cara")
        coach.set_last_name("Coach")
        coach.set_email("cara@example.com")
        coach.set_cell("555-0111")
        coach.save()

        self.assertEqual(str(coach), "Cara Coach")
        self.assertEqual(coach.get_first_name(), "Cara")
        self.assertEqual(coach.get_last_name(), "Coach")
        self.assertEqual(coach.get_email(), "cara@example.com")
        self.assertEqual(coach.get_cell(), "555-0111")

        season = Season.objects.create(year=2031)
        coach.set_seasons([season])
        self.assertEqual(list(coach.get_seasons()), [season])
        self.assertEqual(list(coach.get_practices()), [])


class TfkStaffModelTests(TestCase):
    def test_str(self):
        staff = TfkStaff.objects.create(
            first_name="Sam", last_name="Staffer", email="sam@example.com"
        )
        self.assertEqual(str(staff), "Sam Staffer")


class MentorModelTests(TestCase):
    def test_str_and_getters_setters(self):
        mentor = Mentor()
        mentor.set_first_name("Mel")
        mentor.set_last_name("Mentor")
        mentor.set_email("mel@example.com")
        mentor.set_cell_phone("555-0222")
        mentor.set_type(MentorTypes.REMOTE)
        mentor.set_pace(PaceTypes.NINE.value)
        mentor.set_split_practice(True)
        mentor.save()

        self.assertEqual(str(mentor), "Mel Mentor")
        self.assertEqual(mentor.get_first_name(), "Mel")
        self.assertEqual(mentor.get_last_name(), "Mentor")
        self.assertEqual(mentor.get_email(), "mel@example.com")
        self.assertEqual(mentor.get_cell_phone(), "555-0222")
        self.assertEqual(mentor.get_type(), MentorTypes.REMOTE)
        self.assertEqual(mentor.get_pace(), PaceTypes.NINE.value)
        self.assertTrue(mentor.get_split_practice())

        season = Season.objects.create(year=2032)
        mentor.set_seasons([season])
        self.assertEqual(list(mentor.get_seasons()), [season])

    def test_clean_requires_pace_for_at_practice_mentor(self):
        mentor = Mentor(
            first_name="No",
            last_name="Pace",
            email="nopace@example.com",
            cell_phone="555-0333",
            type=MentorTypes.PRACTICE,
            pace="",
        )
        with self.assertRaises(ValidationError):
            mentor.clean()

    def test_clean_requires_cell_phone_for_at_practice_mentor(self):
        mentor = Mentor(
            first_name="No",
            last_name="Cell",
            email="nocell@example.com",
            cell_phone="",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.TEN.value,
        )
        with self.assertRaises(ValidationError):
            mentor.clean()

    def test_clean_allows_remote_mentor_without_pace_or_cell(self):
        mentor = Mentor(
            first_name="Remote",
            last_name="Mentor",
            email="remote@example.com",
            cell_phone="",
            type=MentorTypes.REMOTE,
            pace="",
        )
        mentor.clean()  # should not raise


class PracticeModelTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2033)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=2),
            season=self.season,
        )

    def test_str_is_date(self):
        self.assertEqual(str(self.practice), str(self.practice.date))

    def test_getters_and_setters(self):
        other_season = Season.objects.create(year=2034)
        self.practice.set_date(self.practice.date)
        self.practice.set_nyrr_race("NYC Half")
        self.practice.set_description("Long run")
        self.practice.set_start_location("Central Park")
        self.practice.set_full_practice(False)
        self.practice.set_show_to_mentors(True)
        self.practice.set_season(other_season)

        self.assertEqual(self.practice.get_nyrr_race(), "NYC Half")
        self.assertEqual(self.practice.get_description(), "Long run")
        self.assertEqual(self.practice.get_start_location(), "Central Park")
        self.assertFalse(self.practice.get_full_practice())
        self.assertTrue(self.practice.get_show_to_mentors())
        self.assertEqual(self.practice.get_season(), other_season)
        self.assertEqual(self.practice.get_date(), self.practice.date)

        mentor = Mentor.objects.create(
            first_name="Set",
            last_name="Mentors",
            email="setmentors@example.com",
            cell_phone="555-0400",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.EIGHT.value,
        )
        self.practice.set_mentors([mentor])
        self.assertEqual(list(self.practice.get_mentors()), [mentor])

    def test_mark_mentor_attending_requires_valid_pace(self):
        mentor = Mentor.objects.create(
            first_name="Bad",
            last_name="Pace",
            email="badpace@example.com",
            cell_phone="555-0401",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        mentor.seasons.add(self.season)
        with self.assertRaises(ValidationError):
            self.practice.mark_mentor_attending(mentor, "not-a-pace")

    def test_update_mentor_pace_requires_valid_pace(self):
        mentor = Mentor.objects.create(
            first_name="Update",
            last_name="Pace",
            email="updatepace@example.com",
            cell_phone="555-0402",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        mentor.seasons.add(self.season)
        with self.assertRaises(ValidationError):
            self.practice.update_mentor_pace(mentor, "bogus")

    def test_update_mentor_pace_raises_when_not_assigned(self):
        mentor = Mentor.objects.create(
            first_name="Unassigned",
            last_name="Mentor",
            email="unassigned@example.com",
            cell_phone="555-0403",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        mentor.seasons.add(self.season)
        with self.assertRaises(ValidationError):
            self.practice.update_mentor_pace(mentor, PaceTypes.NINE.value)

    def test_update_mentor_pace_updates_direct_assignment(self):
        mentor = Mentor.objects.create(
            first_name="Direct",
            last_name="Assign",
            email="directassign@example.com",
            cell_phone="555-0404",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        mentor.seasons.add(self.season)
        self.practice.assign_mentor(mentor, PaceTypes.NINE.value)

        result = self.practice.update_mentor_pace(mentor, PaceTypes.TEN.value)
        self.assertEqual(result.pace, PaceTypes.TEN.value)

    def test_mentor_ids_on_practice_includes_available(self):
        mentor = Mentor.objects.create(
            first_name="Avail",
            last_name="Mentor",
            email="availmentor@example.com",
            cell_phone="555-0405",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        mentor.seasons.add(self.season)
        self.practice.mark_mentor_available(mentor)
        self.assertIn(mentor.id, self.practice.mentor_ids_on_practice())

    def test_swap_assigned_mentor_rejects_same_mentor(self):
        mentor = Mentor.objects.create(
            first_name="Same",
            last_name="Mentor",
            email="samemem@example.com",
            cell_phone="555-0406",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        mentor.seasons.add(self.season)
        self.practice.assign_mentor(mentor, PaceTypes.NINE.value)
        with self.assertRaises(ValidationError):
            self.practice.swap_assigned_mentor(mentor, mentor)

    def test_swap_assigned_mentor_rejects_outgoing_not_assigned(self):
        outgoing = Mentor.objects.create(
            first_name="Out",
            last_name="Unassigned",
            email="outunassigned@example.com",
            cell_phone="555-0407",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        incoming = Mentor.objects.create(
            first_name="In",
            last_name="Coming",
            email="swapincoming@example.com",
            cell_phone="555-0408",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.EIGHT.value,
        )
        outgoing.seasons.add(self.season)
        incoming.seasons.add(self.season)
        with self.assertRaises(ValidationError):
            self.practice.swap_assigned_mentor(outgoing, incoming)

    def test_swap_assigned_mentor_rejects_incoming_already_assigned(self):
        outgoing = Mentor.objects.create(
            first_name="Out",
            last_name="Going",
            email="swapoutgoing@example.com",
            cell_phone="555-0409",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        incoming = Mentor.objects.create(
            first_name="Already",
            last_name="Assigned",
            email="swapalready@example.com",
            cell_phone="555-0410",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.EIGHT.value,
        )
        outgoing.seasons.add(self.season)
        incoming.seasons.add(self.season)
        self.practice.assign_mentor(outgoing, PaceTypes.NINE.value)
        self.practice.assign_mentor(incoming, PaceTypes.EIGHT.value)
        with self.assertRaises(ValidationError):
            self.practice.swap_assigned_mentor(outgoing, incoming)

    def test_swap_assigned_mentor_rejects_incoming_outside_season(self):
        outgoing = Mentor.objects.create(
            first_name="Out",
            last_name="Season",
            email="swapoutseason@example.com",
            cell_phone="555-0411",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        other_season = Season.objects.create(year=2035)
        incoming = Mentor.objects.create(
            first_name="Outside",
            last_name="Season",
            email="swapoutsideseason@example.com",
            cell_phone="555-0412",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.EIGHT.value,
        )
        outgoing.seasons.add(self.season)
        incoming.seasons.add(other_season)
        self.practice.assign_mentor(outgoing, PaceTypes.NINE.value)
        with self.assertRaises(ValidationError):
            self.practice.swap_assigned_mentor(outgoing, incoming)

    def test_get_or_create_mentor_reply_token_requires_scheduled_email(self):
        mentor = Mentor.objects.create(
            first_name="No",
            last_name="Scheduled",
            email="noscheduled@example.com",
            cell_phone="555-0413",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        mentor.seasons.add(self.season)
        with self.assertRaises(ValidationError):
            self.practice.get_or_create_mentor_reply_token(mentor)

    def test_get_or_create_mentor_reply_token_returns_token(self):
        mentor = Mentor.objects.create(
            first_name="Has",
            last_name="Scheduled",
            email="hasscheduled@example.com",
            cell_phone="555-0414",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        mentor.seasons.add(self.season)
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_season=self.season,
        )
        scheduled.practices.add(self.practice)
        token = self.practice.get_or_create_mentor_reply_token(mentor)
        self.assertIsInstance(token, ScheduledEmailMentorToken)

    def test_current_for_attendance_with_explicit_now(self):
        found = Practice.current_for_attendance(now=self.practice.date - timedelta(hours=1))
        self.assertEqual(found, self.practice)


class CoachPracticeAssignmentModelTests(TestCase):
    def test_clean_rejects_coach_missing_practice_season(self):
        season = Season.objects.create(year=2036)
        other_season = Season.objects.create(year=2037)
        coach = Coach.objects.create(
            first_name="Wrong",
            last_name="Season",
            email="wrongseason@example.com",
        )
        coach.seasons.add(other_season)
        practice = Practice.objects.create(date=timezone.now(), season=season)
        assignment = CoachPracticeAssignment(coach=coach, practice=practice)
        with self.assertRaises(ValidationError):
            assignment.clean()


class MentorPracticeAssignmentModelTests(TestCase):
    def test_clean_rejects_mentor_missing_practice_season(self):
        season = Season.objects.create(year=2038)
        other_season = Season.objects.create(year=2039)
        mentor = Mentor.objects.create(
            first_name="Wrong",
            last_name="Season",
            email="wrongseasonmentor@example.com",
            cell_phone="555-0500",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        mentor.seasons.add(other_season)
        practice = Practice.objects.create(date=timezone.now(), season=season)
        assignment = MentorPracticeAssignment(
            mentor=mentor, practice=practice, pace=PaceTypes.NINE.value
        )
        with self.assertRaises(ValidationError):
            assignment.clean()


class MentorPracticeShowUpModelTests(TestCase):
    def test_clean_rejects_unassigned_mentor(self):
        season = Season.objects.create(year=2040)
        practice = Practice.objects.create(date=timezone.now(), season=season)
        mentor = Mentor.objects.create(
            first_name="Not",
            last_name="Assigned",
            email="notassignedshowup@example.com",
            cell_phone="555-0501",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        show_up = MentorPracticeShowUp(
            mentor=mentor, practice=practice, show_up=ShowUpStatus.ATTENDED
        )
        with self.assertRaises(ValidationError):
            show_up.clean()

    def test_clean_allows_found_replacement_regardless_of_assignment(self):
        season = Season.objects.create(year=2041)
        practice = Practice.objects.create(date=timezone.now(), season=season)
        mentor = Mentor.objects.create(
            first_name="Replacement",
            last_name="Found",
            email="foundreplacement@example.com",
            cell_phone="555-0502",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        show_up = MentorPracticeShowUp(
            mentor=mentor,
            practice=practice,
            show_up=ShowUpStatus.FOUND_REPLACEMENT,
        )
        show_up.clean()  # should not raise


class RequestsModelTests(TestCase):
    def test_str_and_getters_setters(self):
        season = Season.objects.create(year=2042)
        practice = Practice.objects.create(date=timezone.now(), season=season)
        req = Requests.objects.create(date=timezone.now(), season=season)
        req.set_date(req.date)
        req.set_season(season)
        req.set_practices([practice])

        self.assertEqual(str(req), str(req.date))
        self.assertEqual(req.get_date(), req.date)
        self.assertEqual(req.get_season(), season)
        self.assertEqual(list(req.get_practices()), [practice])


class RequestsSentLogModelTests(TestCase):
    def test_str_and_getters_setters(self):
        season = Season.objects.create(year=2043)
        mentor = Mentor.objects.create(
            first_name="Log",
            last_name="Mentor",
            email="logmentor@example.com",
            cell_phone="555-0600",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        req = Requests.objects.create(date=timezone.now(), season=season)
        log = RequestsSentLog.objects.create(
            date=timezone.now(), request=req, mentor=mentor
        )
        log.set_date(log.date)
        log.set_status("sent")
        log.set_request(req)
        log.set_mentor(mentor)

        self.assertEqual(str(log), str(log.date))
        self.assertEqual(log.get_date(), log.date)
        self.assertEqual(log.get_status(), "sent")
        self.assertEqual(log.get_request(), req)
        self.assertEqual(log.get_mentor(), mentor)


class MentorAnswersModelTests(TestCase):
    def test_str_and_getters_setters(self):
        season = Season.objects.create(year=2044)
        mentor = Mentor.objects.create(
            first_name="Answer",
            last_name="Mentor",
            email="answermentor@example.com",
            cell_phone="555-0601",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        req = Requests.objects.create(date=timezone.now(), season=season)
        answer = MentorAnswers.objects.create(
            date=timezone.now(),
            request=req,
            season=season,
            mentor=mentor,
            pace=PaceTypes.NINE.value,
            comments="Looking forward to it",
        )
        answer.set_date(answer.date)
        answer.set_practices("sent")
        answer.set_request(req)
        answer.set_season(season)
        answer.set_mentor(mentor)
        answer.set_pace(PaceTypes.TEN.value)
        answer.set_might_come_to_practice(True)
        answer.set_cant_make_practice(False)
        answer.set_comments("Updated comment")

        self.assertEqual(str(answer), str(answer.date))
        self.assertEqual(answer.get_date(), answer.date)
        self.assertEqual(answer.get_practices(), "sent")
        self.assertEqual(answer.get_request(), req)
        self.assertEqual(answer.get_season(), season)
        self.assertEqual(answer.get_mentor(), mentor)
        self.assertEqual(answer.get_pace(), PaceTypes.TEN.value)
        self.assertTrue(answer.get_might_come_to_practice())
        self.assertFalse(answer.get_cant_make_practice())
        self.assertEqual(answer.get_comments(), "Updated comment")


class PracticeReminderModelStrTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2045)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=self.season
        )

    def test_practice_reminder_email_str(self):
        reminder = PracticeReminderEmail.objects.create(
            season=self.season,
            kind=PracticeReminderKind.AFTER_PRACTICE,
            anchor_practice=self.practice,
            practice_one=self.practice,
            subject="Reminder",
            body_text="Body",
        )
        self.assertIn(str(reminder.anchor_practice_id), str(reminder))
        self.assertIn(PracticeReminderKind.AFTER_PRACTICE, str(reminder))

    def test_practice_reminder_suppression_str(self):
        suppression = PracticeReminderSuppression.objects.create(
            season=self.season,
            anchor_practice=self.practice,
            kind=PracticeReminderKind.AFTER_PRACTICE,
        )
        self.assertIn("Suppressed", str(suppression))

    def test_practice_reminder_send_record_str(self):
        reminder = PracticeReminderEmail.objects.create(
            season=self.season,
            kind=PracticeReminderKind.BEFORE_FIRST,
            anchor_practice=self.practice,
            practice_one=self.practice,
            subject="Reminder",
            body_text="Body",
        )
        record = PracticeReminderSendRecord.objects.create(
            reminder=reminder,
            recipient_email="record@example.com",
            recipient_kind=PracticeReminderRecipientKind.MENTOR,
            rendered_subject="Subject",
            rendered_body="Body",
            sent_at=timezone.now(),
        )
        self.assertIn("record@example.com", str(record))


class ScheduledEmailModelTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2046)
        self.mentor = Mentor.objects.create(
            first_name="Sched",
            last_name="Mentor",
            email="schedmentor@example.com",
            cell_phone="555-0700",
            type=MentorTypes.PRACTICE,
            pace=PaceTypes.NINE.value,
        )
        self.mentor.seasons.add(self.season)
        self.practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=self.season
        )
        self.scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="Hi {{ first_name }} {{ last_name }}, pace {{ pace }} "
            "for {{ year }}: {{ link }}",
            recipient_season=self.season,
        )

    def test_str(self):
        self.assertIn("Scheduled email", str(self.scheduled))

    def test_getters_and_setters(self):
        self.scheduled.set_scheduled_send_at(self.scheduled.scheduled_send_at)
        self.scheduled.set_task_completed_at(timezone.now())
        self.scheduled.set_body_text("New body")
        self.scheduled.set_practices([self.practice])
        self.scheduled.set_recipient_mode("specific_mentors")
        self.scheduled.set_recipient_season(self.season)
        self.scheduled.set_specific_mentors([self.mentor])

        self.assertEqual(self.scheduled.get_body_text(), "New body")
        self.assertEqual(list(self.scheduled.get_practices()), [self.practice])
        self.assertEqual(self.scheduled.get_recipient_mode(), "specific_mentors")
        self.assertEqual(self.scheduled.get_recipient_season(), self.season)
        self.assertEqual(list(self.scheduled.get_specific_mentors()), [self.mentor])
        self.assertIsNotNone(self.scheduled.get_task_completed_at())
        self.assertIsNotNone(self.scheduled.get_scheduled_send_at())

    def test_clean_requires_season_for_all_in_season_modes(self):
        scheduled = ScheduledEmail(
            scheduled_send_at=timezone.now(),
            body_text="Hi",
        )
        with self.assertRaises(ValidationError):
            scheduled.clean()

    def test_clean_requires_specific_mentors_when_saved(self):
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="Hi",
            recipient_mode="specific_mentors",
        )
        with self.assertRaises(ValidationError):
            scheduled.clean()

    def test_get_target_mentors_filters_by_type(self):
        remote_mentor = Mentor.objects.create(
            first_name="Remote",
            last_name="Target",
            email="remotetarget@example.com",
            type=MentorTypes.REMOTE,
        )
        remote_mentor.seasons.add(self.season)
        self.scheduled.recipient_mode = "all_at_practice_in_season"
        self.scheduled.save(update_fields=["recipient_mode"])
        targets = list(self.scheduled.get_target_mentors())
        self.assertIn(self.mentor, targets)
        self.assertNotIn(remote_mentor, targets)

        self.scheduled.recipient_mode = "all_remote_in_season"
        self.scheduled.save(update_fields=["recipient_mode"])
        targets = list(self.scheduled.get_target_mentors())
        self.assertIn(remote_mentor, targets)
        self.assertNotIn(self.mentor, targets)

    def test_get_target_mentors_empty_without_season(self):
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="Hi",
        )
        self.assertEqual(list(scheduled.get_target_mentors()), [])

    def test_pending_mentors_for_reminder_excludes_blank_email(self):
        no_email_mentor = Mentor.objects.create(
            first_name="No",
            last_name="Email",
            email="",
            type=MentorTypes.REMOTE,
        )
        no_email_mentor.seasons.add(self.season)
        self.scheduled.sync_mentor_tokens()
        pending = list(self.scheduled.pending_mentors_for_reminder())
        pending_emails = {mentor.email for mentor in pending}
        self.assertNotIn("", pending_emails)

    def test_pending_mentors_alias(self):
        self.scheduled.sync_mentor_tokens()
        self.assertEqual(
            list(self.scheduled.pending_mentors()),
            list(self.scheduled.query_pending_mentors()),
        )

    def test_reply_stats_summary_matches_reply_stats(self):
        self.scheduled.sync_mentor_tokens()
        summary = self.scheduled.reply_stats_summary()
        full = self.scheduled.reply_stats()
        self.assertEqual(summary["mentors_emailed"], full["mentors_emailed"])
        self.assertEqual(summary["mentors_replied"], full["mentors_replied"])

    def test_reply_stats_summaries_for_empty_list_returns_empty_dict(self):
        self.assertEqual(ScheduledEmail.reply_stats_summaries_for([]), {})
        self.assertEqual(ScheduledEmail.reply_stats_summaries_for([None]), {})

    def test_reply_stats_summaries_for_unsaved_email_uses_specific_mentors(self):
        specific_scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="Hi",
        )
        specific_scheduled.specific_mentors.add(self.mentor)
        summaries = ScheduledEmail.reply_stats_summaries_for([specific_scheduled])
        self.assertEqual(
            summaries[specific_scheduled.pk]["mentors_emailed"], 1
        )

    def test_reply_stats_summaries_for_completed_email_with_no_tokens(self):
        completed = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="Hi",
            recipient_season=self.season,
            task_completed_at=timezone.now(),
        )
        summaries = ScheduledEmail.reply_stats_summaries_for([completed])
        self.assertEqual(summaries[completed.pk]["mentors_emailed"], 0)

    def test_resolve_season_year_falls_back_to_linked_practice(self):
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="Hi",
        )
        scheduled.practices.add(self.practice)
        self.assertEqual(scheduled.resolve_season_year(), self.season.year)

    def test_resolve_season_year_none_without_season_or_practice(self):
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="Hi",
        )
        self.assertIsNone(scheduled.resolve_season_year())

    def test_resolve_pace_for_mentor_falls_back_to_mentor_pace(self):
        self.assertEqual(
            self.scheduled.resolve_pace_for_mentor(self.mentor), self.mentor.pace
        )

    def test_render_body_for_mentor_fills_placeholders(self):
        self.scheduled.practices.add(self.practice)
        body = self.scheduled.render_body_for_mentor(self.mentor)
        self.assertIn(self.mentor.first_name, body)
        self.assertIn(self.mentor.last_name, body)
        self.assertIn(str(self.season.year), body)

    def test_render_reminder_body_without_year(self):
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="Hi",
        )
        body = scheduled.render_reminder_body_for_mentor(self.mentor)
        self.assertIn("This is a reminder about mentor practice availability.", body)

    def test_render_reminder_body_with_year(self):
        body = self.scheduled.render_reminder_body_for_mentor(self.mentor)
        self.assertIn(str(self.season.year), body)


class ScheduledEmailMentorTokenModelTests(TestCase):
    def test_str(self):
        season = Season.objects.create(year=2047)
        mentor = Mentor.objects.create(
            first_name="Token",
            last_name="Mentor",
            email="tokenmentor@example.com",
            type=MentorTypes.REMOTE,
        )
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="Hi",
            recipient_season=season,
        )
        token = ScheduledEmailMentorToken.objects.create(
            scheduled_email=scheduled, mentor=mentor
        )
        self.assertIn(str(scheduled.id), str(token))
        self.assertIn(str(mentor.id), str(token))

    def test_practice_reply_save_normalizes_pace(self):
        season = Season.objects.create(year=2048)
        mentor = Mentor.objects.create(
            first_name="Reply",
            last_name="Mentor",
            email="replymentor@example.com",
            type=MentorTypes.REMOTE,
        )
        practice = Practice.objects.create(date=timezone.now(), season=season)
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="Hi",
            recipient_season=season,
        )
        token = ScheduledEmailMentorToken.objects.create(
            scheduled_email=scheduled, mentor=mentor
        )
        reply = ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token,
            mentor=mentor,
            practice=practice,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="8--9",
        )
        self.assertEqual(reply.pace, "8-9")


class MentorCellPhoneRequestModelTests(TestCase):
    def test_send_str(self):
        send = MentorCellPhoneRequestSend.objects.create(sent_at=timezone.now())
        self.assertIn(str(send.id), str(send))

    def test_token_str_and_usable(self):
        mentor = Mentor.objects.create(
            first_name="Cell",
            last_name="Mentor",
            email="cellmentor@example.com",
            type=MentorTypes.REMOTE,
        )
        send = MentorCellPhoneRequestSend.objects.create(sent_at=timezone.now())
        token = MentorCellPhoneRequestToken.objects.create(
            send=send, mentor=mentor, sent_at=timezone.now()
        )
        self.assertIn(str(token.token), str(token))
        self.assertIn(str(mentor.id), str(token))
        self.assertTrue(token.is_usable)
        token.used_at = timezone.now()
        self.assertFalse(token.is_usable)


class MentorSwapRequestModelTests(TestCase):
    def test_str_and_urls(self):
        season = Season.objects.create(year=2049)
        practice = Practice.objects.create(date=timezone.now(), season=season)
        outgoing = Mentor.objects.create(
            first_name="Out", last_name="Going", email="swapstrout@example.com"
        )
        incoming = Mentor.objects.create(
            first_name="In", last_name="Coming", email="swapstrin@example.com"
        )
        swap = MentorSwapRequest.objects.create(
            practice=practice,
            outgoing_mentor=outgoing,
            incoming_mentor=incoming,
            status=MentorSwapRequestStatus.PENDING,
        )
        self.assertIn(str(swap.id), str(swap))
        self.assertIn(str(swap.token), swap.approve_absolute_url())
        self.assertIn(str(swap.token), swap.reject_absolute_url())
        self.assertIn(f"swap={swap.id}", swap.reports_absolute_url())


class UnderfilledPaceModelTests(TestCase):
    def test_send_str(self):
        send = UnderfilledPaceMentorEmailSend.objects.create(sent_at=timezone.now())
        self.assertIn(str(send.id), str(send))

    def test_token_str_and_is_open(self):
        mentor = Mentor.objects.create(
            first_name="Underfilled",
            last_name="Mentor",
            email="underfilledmentor@example.com",
            type=MentorTypes.REMOTE,
        )
        send = UnderfilledPaceMentorEmailSend.objects.create(sent_at=timezone.now())
        token = UnderfilledPaceMentorEmailToken.objects.create(
            send=send, mentor=mentor, sent_at=timezone.now()
        )
        self.assertIn(str(token.token), str(token))
        self.assertTrue(token.is_open)
        token.responded_at = timezone.now()
        self.assertFalse(token.is_open)
        self.assertIn("token=", token.absolute_url())
