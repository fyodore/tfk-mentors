"""Coverage for models.py branches not exercised by the main model/feature
test suites (defensive edge cases, stats fallbacks, direct show-up API)."""

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
    ScheduledEmailRecipientMode,
    Season,
    ShowUpStatus,
)


class MentorIdsOnPracticeAvailableReplyTests(TestCase):
    def test_includes_mentor_from_available_reply(self):
        season = Season.objects.create(year=2600)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=season
        )
        mentor = Mentor.objects.create(
            first_name="Avail",
            last_name="Reply",
            email="availreply@example.com",
            cell_phone="555-0010",
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
        self.assertIn(mentor.id, practice.mentor_ids_on_practice())


class SwapAssignedMentorNoResolvablePaceTests(TestCase):
    def test_raises_when_outgoing_mentor_has_no_pace_anywhere(self):
        season = Season.objects.create(year=2601)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=season
        )
        outgoing = Mentor.objects.create(
            first_name="No",
            last_name="Pace",
            email="nopaceswap@example.com",
            type=MentorTypes.PRACTICE,
            pace="",
        )
        incoming = Mentor.objects.create(
            first_name="In",
            last_name="Coming",
            email="incomingnopace@example.com",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        for mentor in (outgoing, incoming):
            mentor.seasons.add(season)
        # Direct assignment with a blank pace and a mentor whose default pace
        # is also blank: neither the roster entry nor the outgoing.pace
        # fallback can resolve a usable pace. Use update() to bypass the
        # model's own blank=False validation on pace.
        assignment = MentorPracticeAssignment.objects.create(
            mentor=outgoing, practice=practice, pace="9-10"
        )
        MentorPracticeAssignment.objects.filter(pk=assignment.pk).update(pace="")
        with self.assertRaises(Exception):
            practice.swap_assigned_mentor(outgoing, incoming)


class AttendingRosterFoundReplacementDirectApiTests(TestCase):
    """A found-replacement show-up recorded directly (without going through
    swap_assigned_mentor's remove_mentor call) leaves the underlying reply or
    assignment row intact, exercising the swapped-out exclusion checks in
    attending_mentor_roster_entries()."""

    def setUp(self):
        self.client = APIClient()
        session = self.client.session
        session["site_authenticated"] = True
        session.save()
        self.season = Season.objects.create(year=2602)
        self.practice = Practice.objects.create(
            date=timezone.now() - timedelta(hours=2), season=self.season
        )

    def _mark_found_replacement(self, mentor):
        response = self.client.patch(
            f"/api/practice-attendance/{self.practice.id}/",
            {
                "mentors": [
                    {
                        "mentor_id": mentor.id,
                        "show_up": ShowUpStatus.FOUND_REPLACEMENT,
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_excludes_reply_based_mentor_marked_found_replacement(self):
        mentor = Mentor.objects.create(
            first_name="Reply",
            last_name="Swapped",
            email="replyswapped@example.com",
            cell_phone="555-0011",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        mentor.seasons.add(self.season)
        scheduled = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_season=self.season,
        )
        scheduled.practices.add(self.practice)
        scheduled.sync_mentor_tokens()
        token = ScheduledEmailMentorToken.objects.get(
            scheduled_email=scheduled, mentor=mentor
        )
        ScheduledEmailMentorPracticeReply.objects.create(
            mentor_token=token,
            mentor=mentor,
            practice=self.practice,
            attendance=PracticeAttendanceReply.ATTENDING,
            pace="9-10",
        )
        self.assertIn(mentor.id, self.practice.assigned_mentor_ids())

        self._mark_found_replacement(mentor)

        self.assertNotIn(mentor.id, self.practice.assigned_mentor_ids())

    def test_excludes_direct_assignment_mentor_marked_found_replacement(self):
        mentor = Mentor.objects.create(
            first_name="Direct",
            last_name="Swapped",
            email="directswapped@example.com",
            cell_phone="555-0012",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        mentor.seasons.add(self.season)
        MentorPracticeAssignment.objects.create(
            mentor=mentor, practice=self.practice, pace="9-10"
        )
        self.assertIn(mentor.id, self.practice.assigned_mentor_ids())

        self._mark_found_replacement(mentor)

        self.assertNotIn(mentor.id, self.practice.assigned_mentor_ids())


class GetTargetMentorsSpecificMentorsTests(TestCase):
    def test_returns_only_specific_mentors(self):
        season = Season.objects.create(year=2603)
        included = Mentor.objects.create(
            first_name="Included",
            last_name="Mentor",
            email="includedtarget@example.com",
            type=MentorTypes.REMOTE,
        )
        excluded = Mentor.objects.create(
            first_name="Excluded",
            last_name="Mentor",
            email="excludedtarget@example.com",
            type=MentorTypes.REMOTE,
        )
        for mentor in (included, excluded):
            mentor.seasons.add(season)
        email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_mode=ScheduledEmailRecipientMode.SPECIFIC_MENTORS,
        )
        email.specific_mentors.add(included)
        targets = list(email.get_target_mentors())
        self.assertEqual(targets, [included])


class SendTimeMentorTokenQuerysetTests(TestCase):
    def setUp(self):
        self.season = Season.objects.create(year=2604)
        self.email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_season=self.season,
        )

    def test_returns_all_tokens_when_not_yet_sent(self):
        mentor = Mentor.objects.create(
            first_name="Unsent",
            last_name="Token",
            email="unsenttoken@example.com",
            type=MentorTypes.REMOTE,
        )
        ScheduledEmailMentorToken.objects.create(
            scheduled_email=self.email, mentor=mentor
        )
        tokens = list(self.email._send_time_mentor_token_queryset())
        self.assertEqual(len(tokens), 1)

    def test_filters_by_cutoff_when_sent(self):
        mentor = Mentor.objects.create(
            first_name="Sent",
            last_name="Token",
            email="senttoken@example.com",
            type=MentorTypes.REMOTE,
        )
        self.email.task_completed_at = timezone.now()
        self.email.save(update_fields=["task_completed_at"])
        ScheduledEmailMentorToken.objects.create(
            scheduled_email=self.email, mentor=mentor
        )
        tokens = list(self.email._send_time_mentor_token_queryset())
        self.assertEqual(len(tokens), 1)


class EmailedMentorIdsForStatsFallbackTests(TestCase):
    def test_sent_email_falls_back_to_send_time_tokens(self):
        season = Season.objects.create(year=2605)
        mentor = Mentor.objects.create(
            first_name="Fallback",
            last_name="Sent",
            email="fallbacksent@example.com",
            type=MentorTypes.REMOTE,
        )
        email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_season=season,
            task_completed_at=timezone.now(),
        )
        # Token exists but was never marked included_in_send, and no replies
        # were ever recorded: forces the fallback to the send-time queryset.
        ScheduledEmailMentorToken.objects.create(
            scheduled_email=email, mentor=mentor
        )
        ids = email._emailed_mentor_ids_for_stats()
        self.assertEqual(ids, {mentor.id})

    def test_unsent_email_falls_back_to_get_target_mentors(self):
        season = Season.objects.create(year=2606)
        mentor = Mentor.objects.create(
            first_name="Fallback",
            last_name="Unsent",
            email="fallbackunsent@example.com",
            type=MentorTypes.REMOTE,
        )
        mentor.seasons.add(season)
        email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_season=season,
        )
        # No tokens created (sync_mentor_tokens never called) and no replies.
        ids = email._emailed_mentor_ids_for_stats()
        self.assertEqual(ids, {mentor.id})

    def test_unsent_email_falls_back_to_specific_mentors_when_targets_empty(self):
        season = Season.objects.create(year=2607)
        mentor = Mentor.objects.create(
            first_name="Manual",
            last_name="Specific",
            email="manualspecific@example.com",
            type=MentorTypes.REMOTE,
        )
        email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_mode=ScheduledEmailRecipientMode.ALL_IN_SEASON,
            recipient_season=season,
        )
        # No mentors in the season -> get_target_mentors() is empty, but a
        # mentor was directly attached to specific_mentors out-of-band.
        email.specific_mentors.add(mentor)
        ids = email._emailed_mentor_ids_for_stats()
        self.assertEqual(ids, {mentor.id})

    def test_returns_empty_set_when_no_emailed_mentor_ids(self):
        season = Season.objects.create(year=2608)
        email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_season=season,
        )
        self.assertEqual(email._mentors_replied_ids_for_stats(set()), set())


class ReplyStatsSummariesSpecificMentorsPrefetchTests(TestCase):
    def test_uses_prefetched_specific_mentors_cache_when_no_tokens_or_replies(self):
        mentor = Mentor.objects.create(
            first_name="Prefetched",
            last_name="Specific",
            email="prefetchedspecific@example.com",
            type=MentorTypes.REMOTE,
        )
        email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_mode=ScheduledEmailRecipientMode.SPECIFIC_MENTORS,
        )
        email.specific_mentors.add(mentor)

        prefetched = ScheduledEmail.objects.prefetch_related("specific_mentors").get(
            pk=email.pk
        )
        summaries = ScheduledEmail.reply_stats_summaries_for([prefetched])
        self.assertEqual(summaries[email.pk]["mentors_emailed"], 1)


class ResolvePaceForMentorAssignmentTests(TestCase):
    def test_uses_direct_assignment_pace_over_mentor_default(self):
        season = Season.objects.create(year=2609)
        practice = Practice.objects.create(
            date=timezone.now() + timedelta(days=1), season=season
        )
        mentor = Mentor.objects.create(
            first_name="Assignment",
            last_name="Pace",
            email="assignmentpace@example.com",
            type=MentorTypes.PRACTICE,
            pace="9-10",
        )
        mentor.seasons.add(season)
        MentorPracticeAssignment.objects.create(
            mentor=mentor, practice=practice, pace="8-9"
        )
        email = ScheduledEmail.objects.create(
            scheduled_send_at=timezone.now(),
            body_text="hi",
            recipient_season=season,
        )
        email.practices.add(practice)
        self.assertEqual(email.resolve_pace_for_mentor(mentor), "8-9")
