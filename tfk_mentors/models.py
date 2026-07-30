import re
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

EMAIL_TEMPLATE_PLACEHOLDER_RE = re.compile(
    r"\{\{\s*(first_name|last_name|pace|link|year)\s*\}\}",
    re.IGNORECASE,
)

class MentorTypes(models.TextChoices):
    PRACTICE = "At Practice"
    REMOTE = "Remote"

class PaceTypes(models.TextChoices):
    EIGHT = "8-9"
    NINE = "9-10"
    TEN = "10-11"
    ELEVEN = "11-12"
    TWELVE = "12-13"
    THIRTEEN = "13+"


PACE_SORT = {choice.value: index for index, choice in enumerate(PaceTypes)}

PACE_DASH_CHARS_RE = re.compile(r"[\u2010-\u2015\u2212-]+")


def normalize_pace(raw):
    """Normalize imported pace labels (e.g. 8--9) to a PaceTypes value."""
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    text = re.sub(r"\s+", "", text)
    text = PACE_DASH_CHARS_RE.sub("-", text)
    text = re.sub(r"-+", "-", text)
    text = re.sub(r"\++", "+", text)
    if text.startswith("13"):
        return PaceTypes.THIRTEEN.value
    return text


class ScheduledEmailRecipientMode(models.TextChoices):
    ALL_IN_SEASON = "all_in_season", "All mentors in season"
    ALL_AT_PRACTICE_IN_SEASON = "all_at_practice_in_season", "All At Practice mentors in season"
    ALL_REMOTE_IN_SEASON = "all_remote_in_season", "All Remote mentors in season"
    SPECIFIC_MENTORS = "specific_mentors", "Specific mentors"


class PracticeAttendanceReply(models.TextChoices):
    ATTENDING = "attending", "Attending"
    NOT_ATTENDING = "not_attending", "Not attending"
    FIRST_HALF = "first_half", "First half"
    SECOND_HALF = "second_half", "Second half"
    AVAILABLE = "available", "Available"


class ShowUpStatus(models.TextChoices):
    ATTENDED = "attended", "Attended"
    MISSED = "missed", "Missed"
    FOUND_REPLACEMENT = "found_replacement", "Found Replacement"


class TimeStampedModel(models.Model):
    """Abstract base class that adds created_at and updated_at fields to models."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def get_created_at(self):
        return self.created_at

    def set_created_at(self, value):
        self.created_at = value

    def get_updated_at(self):
        return self.updated_at

    def set_updated_at(self, value):
        self.updated_at = value

class Season(TimeStampedModel):
    """Model for an item with timestamps."""
    year = models.IntegerField()
    is_current = models.BooleanField(
        default=False,
        help_text="When true, this season is the active season for the app.",
    )
    head_coach = models.ForeignKey(
        "Coach",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="head_coach_seasons",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_current"],
                condition=models.Q(is_current=True),
                name="unique_current_season",
            )
        ]

    def __str__(self):
        return str(self.year)

    def save(self, *args, **kwargs):
        if self.is_current:
            Season.objects.filter(is_current=True).exclude(pk=self.pk).update(
                is_current=False
            )
        super().save(*args, **kwargs)

    def get_year(self):
        return self.year

    def set_year(self, value):
        self.year = value

    def get_head_coach(self):
        return self.head_coach

    def set_head_coach(self, value):
        self.head_coach = value


class Coach(TimeStampedModel):
    """Model for an item with timestamps."""

    first_name = models.CharField(max_length=75)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=100)
    cell = models.CharField(max_length=20, blank=True, default="")
    seasons = models.ManyToManyField(Season, related_name="coaches", blank=True)
    practices = models.ManyToManyField(
        "Practice",
        through="CoachPracticeAssignment",
        related_name="coaches",
        blank=True,
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_first_name(self):
        return self.first_name

    def set_first_name(self, value):
        self.first_name = value

    def get_last_name(self):
        return self.last_name

    def set_last_name(self, value):
        self.last_name = value

    def get_email(self):
        return self.email

    def set_email(self, value):
        self.email = value

    def get_cell(self):
        return self.cell

    def set_cell(self, value):
        self.cell = value

    def get_seasons(self):
        return self.seasons.all()

    def set_seasons(self, seasons):
        self.seasons.set(seasons)

    def get_practices(self):
        return self.practices.all()


class TfkStaff(TimeStampedModel):
    """TFK staff contact (admin roster)."""

    first_name = models.CharField(max_length=75)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=100)
    cell_phone = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        ordering = ["last_name", "first_name", "id"]
        verbose_name = "TFK staff"
        verbose_name_plural = "TFK staff"

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_first_name(self):
        return self.first_name

    def set_first_name(self, value):
        self.first_name = value

    def get_last_name(self):
        return self.last_name

    def set_last_name(self, value):
        self.last_name = value

    def get_email(self):
        return self.email

    def set_email(self, value):
        self.email = value

    def get_cell_phone(self):
        return self.cell_phone

    def set_cell_phone(self, value):
        self.cell_phone = value


class Mentor(TimeStampedModel):
    """Model for an item with timestamps."""

    first_name = models.CharField(max_length=75)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=100, unique=True)
    cell_phone = models.CharField(max_length=20, blank=True, default="")
    type = models.CharField(choices=MentorTypes, max_length=11)
    seasons = models.ManyToManyField(Season)
    pace = models.CharField(
        choices=PaceTypes,
        max_length=11,
        blank=True,
        default="",
    )
    split_practice = models.BooleanField(default=False)
    practices = models.ManyToManyField(
        "Practice",
        through="MentorPracticeAssignment",
        related_name="mentor_assignments",
        blank=True,
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_first_name(self):
        return self.first_name

    def set_first_name(self, value):
        self.first_name = value

    def get_last_name(self):
        return self.last_name

    def set_last_name(self, value):
        self.last_name = value

    def get_email(self):
        return self.email

    def set_email(self, value):
        self.email = value

    def get_cell_phone(self):
        return self.cell_phone

    def set_cell_phone(self, value):
        self.cell_phone = value

    def get_type(self):
        return self.type

    def set_type(self, value):
        self.type = value

    def get_pace(self):
        return self.pace

    def set_pace(self, value):
        self.pace = value

    def clean(self):
        super().clean()
        if self.type != MentorTypes.REMOTE and not (self.pace or "").strip():
            raise ValidationError(
                {"pace": "Pace is required for At Practice mentors."}
            )
        if self.type != MentorTypes.REMOTE and not (self.cell_phone or "").strip():
            raise ValidationError(
                {"cell_phone": "Cell phone is required for At Practice mentors."}
            )

    def save(self, *args, **kwargs):
        if self.pace:
            self.pace = normalize_pace(self.pace)
        super().save(*args, **kwargs)

    def get_split_practice(self):
        return self.split_practice

    def set_split_practice(self, value):
        self.split_practice = value

    def get_seasons(self):
        return self.seasons.all()

    def set_seasons(self, seasons):
        self.seasons.set(seasons)

class Practice(TimeStampedModel):
    """Model for an item with timestamps."""
    date = models.DateTimeField()
    nyrr_race = models.CharField(max_length=150, blank=True, default="")
    description = models.TextField(blank=True, default="")
    start_location = models.CharField(max_length=255, blank=True, default="")
    mentors = models.ManyToManyField(Mentor)
    full_practice = models.BooleanField(default=True)
    show_to_mentors = models.BooleanField(
        default=False,
        help_text="When true, this practice appears on the public mentor directory.",
    )
    mentor_selection_closed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "When set, At Practice mentors can no longer change replies for this "
            "practice via their email link (set when the schedule is applied)."
        ),
    )
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    attendance_comments = models.TextField(
        blank=True,
        default="",
        help_text="General notes recorded on the practice attendance page.",
    )

    def __str__(self):
        return str(self.date)

    def get_date(self):
        return self.date

    def set_date(self, value):
        self.date = value

    def get_nyrr_race(self):
        return self.nyrr_race

    def set_nyrr_race(self, value):
        self.nyrr_race = value

    def get_description(self):
        return self.description

    def set_description(self, value):
        self.description = value

    def get_start_location(self):
        return self.start_location

    def set_start_location(self, value):
        self.start_location = value

    def get_full_practice(self):
        return self.full_practice

    def set_full_practice(self, value):
        self.full_practice = value

    def get_show_to_mentors(self):
        return self.show_to_mentors

    def set_show_to_mentors(self, value):
        self.show_to_mentors = value

    def get_season(self):
        return self.season

    def set_season(self, season):
        self.season = season

    def get_mentors(self):
        return self.mentors.all()

    def set_mentors(self, mentors):
        self.mentors.set(mentors)

    def _latest_reply_by_mentor(self):
        """Most recent email reply per mentor for this practice."""
        latest_by_mentor = {}
        for reply in (
            self.mentor_email_replies.select_related(
                "mentor", "mentor_token__scheduled_email"
            ).order_by("-updated_at")
        ):
            if reply.mentor_id not in latest_by_mentor:
                latest_by_mentor[reply.mentor_id] = reply
        return latest_by_mentor

    def _latest_mentor_replies_for_attendance(self, attendance_values):
        """Latest reply per mentor when that mentor's current status matches."""
        attendance_set = frozenset(attendance_values)
        replies = [
            reply
            for reply in self._latest_reply_by_mentor().values()
            if reply.attendance in attendance_set
        ]
        return sorted(
            replies,
            key=lambda reply: (
                PACE_SORT.get(
                    normalize_pace(reply.pace or reply.mentor.pace or ""), 99
                ),
                reply.mentor.last_name,
                reply.mentor.first_name,
            ),
        )

    def latest_attending_mentor_replies(self):
        """Latest attending reply per mentor linked via ScheduledEmailMentorPracticeReply."""
        attending_values = (
            PracticeAttendanceReply.ATTENDING,
            PracticeAttendanceReply.FIRST_HALF,
            PracticeAttendanceReply.SECOND_HALF,
        )
        return self._latest_mentor_replies_for_attendance(attending_values)

    def latest_available_mentor_replies(self):
        """Latest available reply per mentor for this practice."""
        return self._latest_mentor_replies_for_attendance(
            (PracticeAttendanceReply.AVAILABLE,)
        )

    def scheduled_email_for_mentor_replies(self):
        """Scheduled email linked to this practice, if any."""
        scheduled = (
            ScheduledEmail.objects.filter(
                practices=self,
                task_completed_at__isnull=False,
            )
            .order_by("-task_completed_at", "-scheduled_send_at", "-id")
            .first()
        )
        if scheduled is None:
            scheduled = (
                ScheduledEmail.objects.filter(practices=self)
                .order_by("-scheduled_send_at", "-id")
                .first()
            )
        return scheduled

    def assign_mentor(self, mentor, pace):
        """Add or update a mentor on this practice without an email reply."""
        pace = normalize_pace(pace or mentor.pace or "")
        assignment, _ = MentorPracticeAssignment.objects.update_or_create(
            mentor=mentor,
            practice=self,
            defaults={"pace": pace, "is_available": False},
        )
        self.mentors.add(mentor)
        return assignment

    def mark_mentor_available(self, mentor, *, pace=None, sync=True):
        """Move a mentor on this roster to the available list."""
        pace = normalize_pace(pace or mentor.pace or "")
        scheduled = self.scheduled_email_for_mentor_replies()
        if scheduled is not None:
            token, _ = ScheduledEmailMentorToken.objects.get_or_create(
                scheduled_email=scheduled,
                mentor=mentor,
            )
            reply, _ = ScheduledEmailMentorPracticeReply.objects.update_or_create(
                mentor_token=token,
                practice=self,
                defaults={
                    "mentor": mentor,
                    "attendance": PracticeAttendanceReply.AVAILABLE,
                    "pace": pace,
                },
            )
            if sync:
                self.sync_mentor_assignments_from_replies()
            return reply

        assignment, _ = MentorPracticeAssignment.objects.update_or_create(
            mentor=mentor,
            practice=self,
            defaults={"pace": pace, "is_available": True},
        )
        assignment.is_available = True
        assignment.pace = pace
        assignment.save(update_fields=["is_available", "pace", "updated_at"])
        self.mentors.remove(mentor)
        return assignment

    def update_mentor_pace(self, mentor, pace):
        """Update a mentor's pace for this practice only.

        Does not change the mentor profile pace or any other practice.
        """
        from django.utils import timezone

        pace = normalize_pace(pace or "")
        if not pace or pace not in {choice.value for choice in PaceTypes}:
            raise ValidationError("Invalid pace choice.")

        reply_qs = ScheduledEmailMentorPracticeReply.objects.filter(
            practice=self,
            mentor=mentor,
        ).exclude(attendance=PracticeAttendanceReply.NOT_ATTENDING)
        updated_replies = reply_qs.update(pace=pace, updated_at=timezone.now())

        assignment = MentorPracticeAssignment.objects.filter(
            practice=self,
            mentor=mentor,
        ).first()
        if assignment is not None:
            assignment.pace = pace
            assignment.save(update_fields=["pace", "updated_at"])

        if updated_replies:
            self.sync_mentor_assignments_from_replies()
            latest = self._latest_reply_by_mentor().get(mentor.id)
            if latest is not None:
                return latest

        if assignment is not None:
            return assignment

        raise ValidationError("Mentor is not assigned to this practice.")

    def mark_mentor_attending(self, mentor, pace, *, sync=True):
        """Move a mentor back onto this practice roster from available or unassigned."""
        pace = normalize_pace(pace or mentor.pace or "")
        if not pace or pace not in {choice.value for choice in PaceTypes}:
            raise ValidationError("Invalid pace choice.")

        # Clearing found-replacement lets a previously swapped-out mentor rejoin
        # the attending roster used by practice reminders and assignments.
        MentorPracticeShowUp.objects.filter(
            practice=self,
            mentor=mentor,
            show_up=ShowUpStatus.FOUND_REPLACEMENT,
        ).delete()

        latest = self._latest_reply_by_mentor().get(mentor.id)
        if latest is not None and latest.attendance == PracticeAttendanceReply.AVAILABLE:
            latest.attendance = PracticeAttendanceReply.ATTENDING
            latest.pace = pace
            latest.save(update_fields=["attendance", "pace", "updated_at"])
            if sync:
                self.sync_mentor_assignments_from_replies()
            return latest

        available_assignment = MentorPracticeAssignment.objects.filter(
            practice=self,
            mentor=mentor,
            is_available=True,
        ).first()
        if available_assignment is not None:
            available_assignment.pace = pace
            available_assignment.is_available = False
            available_assignment.save(
                update_fields=["pace", "is_available", "updated_at"]
            )
            self.mentors.add(mentor)
            return available_assignment

        if latest is not None and latest.attendance != PracticeAttendanceReply.NOT_ATTENDING:
            latest.attendance = PracticeAttendanceReply.ATTENDING
            latest.pace = pace
            latest.save(update_fields=["attendance", "pace", "updated_at"])
            if sync:
                self.sync_mentor_assignments_from_replies()
            return latest

        scheduled = self.scheduled_email_for_mentor_replies()
        if scheduled is not None:
            token, _ = ScheduledEmailMentorToken.objects.get_or_create(
                scheduled_email=scheduled,
                mentor=mentor,
            )
            reply, _ = ScheduledEmailMentorPracticeReply.objects.update_or_create(
                mentor_token=token,
                practice=self,
                defaults={
                    "mentor": mentor,
                    "attendance": PracticeAttendanceReply.ATTENDING,
                    "pace": pace,
                },
            )
            if sync:
                self.sync_mentor_assignments_from_replies()
            return reply

        return self.assign_mentor(mentor, pace)

    def remove_mentor(self, mentor_id):
        """Remove a mentor from this practice."""
        from django.utils import timezone

        ScheduledEmailMentorPracticeReply.objects.filter(
            practice=self,
            mentor_id=mentor_id,
        ).update(
            attendance=PracticeAttendanceReply.NOT_ATTENDING,
            pace="",
            updated_at=timezone.now(),
        )
        MentorPracticeAssignment.objects.filter(
            practice=self,
            mentor_id=mentor_id,
        ).delete()
        self.mentors.remove(mentor_id)

    def mentor_ids_on_practice(self):
        """Mentor ids on the attending roster or available list."""
        ids = set(self.assigned_mentor_ids())
        for assignment in MentorPracticeAssignment.objects.filter(
            practice=self,
            is_available=True,
        ):
            ids.add(assignment.mentor_id)
        for reply in self.latest_available_mentor_replies():
            ids.add(reply.mentor_id)
        return ids

    def swap_assigned_mentor(self, outgoing, incoming):
        """Replace an assigned mentor; record outgoing as found replacement."""
        if incoming.id == outgoing.id:
            raise ValidationError("Choose a different mentor for the swap.")
        if outgoing.id not in self.assigned_mentor_ids():
            raise ValidationError("Outgoing mentor is not assigned to this practice.")
        if incoming.id in self.assigned_mentor_ids():
            raise ValidationError("Replacement mentor is already assigned to this practice.")
        if not incoming.seasons.filter(id=self.season_id).exists():
            raise ValidationError(
                "Replacement mentor must belong to the practice season."
            )

        pace = ""
        for mentor, entry_pace, _reply, _assignment in self.attending_mentor_roster_entries():
            if mentor.id == outgoing.id:
                pace = entry_pace
                break
        if not pace:
            pace = normalize_pace(outgoing.pace or "")
        if not pace or pace not in {choice.value for choice in PaceTypes}:
            raise ValidationError("Could not determine pace for the outgoing mentor.")

        MentorPracticeShowUp.objects.update_or_create(
            practice=self,
            mentor=outgoing,
            defaults={"show_up": ShowUpStatus.FOUND_REPLACEMENT},
        )
        self.remove_mentor(outgoing.id)
        return self.mark_mentor_attending(incoming, pace)

    def _found_replacement_mentor_ids(self):
        """Mentors recorded as swapped out (found replacement) for this practice."""
        return set(
            self.mentor_show_ups.filter(
                show_up=ShowUpStatus.FOUND_REPLACEMENT,
            ).values_list("mentor_id", flat=True)
        )

    def attending_mentor_roster_entries(self):
        """All attending mentors from email replies and direct assignments.

        Mentors marked found-replacement (swapped out) are excluded so practice
        reminders and rosters list the replacement mentor, not the outgoing one.
        """
        entries = []
        seen = set()
        swapped_out_ids = self._found_replacement_mentor_ids()
        latest_by_mentor = self._latest_reply_by_mentor()
        for reply in self.latest_attending_mentor_replies():
            if reply.mentor_id in swapped_out_ids:
                continue
            mentor = reply.mentor
            pace = normalize_pace(reply.pace or mentor.pace or "")
            entries.append((mentor, pace, reply, None))
            seen.add(mentor.id)

        assignments = MentorPracticeAssignment.objects.filter(
            practice=self
        ).select_related("mentor")
        for assignment in assignments:
            if assignment.mentor_id in seen:
                continue
            if assignment.mentor_id in swapped_out_ids:
                continue
            if assignment.is_available:
                continue
            latest = latest_by_mentor.get(assignment.mentor_id)
            if (
                latest is not None
                and latest.attendance == PracticeAttendanceReply.AVAILABLE
            ):
                continue
            mentor = assignment.mentor
            pace = normalize_pace(assignment.pace or mentor.pace or "")
            entries.append((mentor, pace, None, assignment))
            seen.add(mentor.id)

        return sorted(
            entries,
            key=lambda item: (
                PACE_SORT.get(item[1], 99),
                item[0].last_name,
                item[0].first_name,
            ),
        )

    def sync_mentor_assignments_from_replies(self):
        """Align reply-based assignments; preserve direct admin assignments."""
        swapped_out_ids = self._found_replacement_mentor_ids()
        attending_replies = [
            reply
            for reply in self.latest_attending_mentor_replies()
            if reply.mentor_id not in swapped_out_ids
        ]
        attending_mentor_ids = {reply.mentor_id for reply in attending_replies}
        mentors_with_any_reply = set(
            self.mentor_email_replies.values_list("mentor_id", flat=True)
        )

        MentorPracticeAssignment.objects.filter(
            practice=self,
            mentor_id__in=mentors_with_any_reply,
        ).exclude(
            mentor_id__in=attending_mentor_ids,
        ).delete()
        # Never keep assignments for mentors recorded as swapped out.
        if swapped_out_ids:
            MentorPracticeAssignment.objects.filter(
                practice=self,
                mentor_id__in=swapped_out_ids,
            ).delete()

        for reply in attending_replies:
            pace = normalize_pace(reply.pace or reply.mentor.pace or "")
            MentorPracticeAssignment.objects.update_or_create(
                mentor_id=reply.mentor_id,
                practice=self,
                defaults={"pace": pace, "is_available": False},
            )

        assignment_mentor_ids = list(
            MentorPracticeAssignment.objects.filter(
                practice=self,
                is_available=False,
            )
            .exclude(mentor_id__in=swapped_out_ids)
            .values_list("mentor_id", flat=True)
        )
        self.mentors.set(assignment_mentor_ids)

    @classmethod
    def current_for_attendance(cls, *, now=None):
        """Practice coming up or within the last 24 hours (earliest in window)."""
        if now is None:
            from django.utils import timezone

            now = timezone.now()
        window_start = now - timedelta(hours=24)
        return (
            cls.objects.filter(date__gte=window_start)
            .select_related("season")
            .order_by("date", "id")
            .first()
        )

    def assigned_mentor_ids(self):
        """Mentor ids on the attending roster (not merely available)."""
        return {
            mentor.id for mentor, _pace, _reply, _assignment in self.attending_mentor_roster_entries()
        }

    def get_or_create_mentor_reply_token(self, mentor):
        """Token for storing admin or mentor replies tied to this practice."""
        scheduled = self.scheduled_email_for_mentor_replies()
        if scheduled is None:
            raise ValidationError(
                "Link a scheduled email to this practice before assigning mentors."
            )
        token, _ = ScheduledEmailMentorToken.objects.get_or_create(
            scheduled_email=scheduled,
            mentor=mentor,
        )
        return token


class CoachPracticeAssignment(TimeStampedModel):
    coach = models.ForeignKey(Coach, on_delete=models.CASCADE)
    practice = models.ForeignKey(Practice, on_delete=models.CASCADE)
    pace = models.CharField(
        choices=PaceTypes,
        max_length=11,
        blank=True,
        default="",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["coach", "practice"],
                name="unique_coach_practice_assignment",
            )
        ]

    def clean(self):
        if (
            self.coach_id
            and self.practice_id
            and not self.coach.seasons.filter(id=self.practice.season_id).exists()
        ):
            raise ValidationError(
                "Coach must include the same season as the practice."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class MentorPracticeAssignment(TimeStampedModel):
    mentor = models.ForeignKey(Mentor, on_delete=models.CASCADE)
    practice = models.ForeignKey(Practice, on_delete=models.CASCADE)
    pace = models.CharField(choices=PaceTypes, max_length=11)
    is_available = models.BooleanField(
        default=False,
        help_text=(
            "When true, the mentor is listed as available for this practice "
            "without an email reply row."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["mentor", "practice"],
                name="unique_mentor_practice_assignment",
            )
        ]

    def clean(self):
        if (
            self.mentor_id
            and self.practice_id
            and not self.mentor.seasons.filter(id=self.practice.season_id).exists()
        ):
            raise ValidationError(
                "Mentor must include the same season as the practice."
            )

    def save(self, *args, **kwargs):
        if self.pace:
            self.pace = normalize_pace(self.pace)
        self.full_clean()
        return super().save(*args, **kwargs)


class MentorPracticeShowUp(TimeStampedModel):
    """Whether an assigned mentor actually attended or missed a practice."""

    mentor = models.ForeignKey(Mentor, on_delete=models.CASCADE)
    practice = models.ForeignKey(
        Practice,
        on_delete=models.CASCADE,
        related_name="mentor_show_ups",
    )
    show_up = models.CharField(max_length=20, choices=ShowUpStatus.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["mentor", "practice"],
                name="unique_mentor_practice_show_up",
            )
        ]

    def clean(self):
        if self.mentor_id and self.practice_id:
            if self.show_up == ShowUpStatus.FOUND_REPLACEMENT:
                return
            if self.mentor_id not in self.practice.assigned_mentor_ids():
                raise ValidationError(
                    "Show-up can only be recorded for mentors assigned to this practice."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Requests(TimeStampedModel):
    """Model for an item with timestamps."""
    date = models.DateTimeField()
    practices = models.ManyToManyField(Practice)
    season = models.ForeignKey(Season, on_delete=models.CASCADE)

    def __str__(self):
        return str(self.date)

    def get_date(self):
        return self.date

    def set_date(self, value):
        self.date = value

    def get_season(self):
        return self.season

    def set_season(self, season):
        self.season = season

    def get_practices(self):
        return self.practices.all()

    def set_practices(self, practices):
        self.practices.set(practices)

class RequestsSentLog(TimeStampedModel):
    """Model for an item with timestamps."""
    date = models.DateTimeField()
    status = models.CharField(max_length=4, default="sent")
    request = models.ForeignKey(Requests, on_delete=models.CASCADE)
    mentor = models.ForeignKey(Mentor, on_delete=models.CASCADE)

    def __str__(self):
        return str(self.date)

    def get_date(self):
        return self.date

    def set_date(self, value):
        self.date = value

    def get_status(self):
        return self.status

    def set_status(self, value):
        self.status = value

    def get_request(self):
        return self.request

    def set_request(self, request):
        self.request = request

    def get_mentor(self):
        return self.mentor

    def set_mentor(self, mentor):
        self.mentor = mentor

class MentorAnswers(TimeStampedModel):
    """Model for an item with timestamps."""
    date = models.DateTimeField()
    practices = models.CharField(max_length=4, default="sent")
    request = models.ForeignKey(Requests, on_delete=models.CASCADE)
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    mentor = models.ForeignKey(Mentor, on_delete=models.CASCADE)
    pace = models.CharField(choices=PaceTypes, max_length=5)
    might_come_to_practice = models.BooleanField(default=False)
    cant_make_practice = models.BooleanField(default=False)
    comments = models.TextField()

    def __str__(self):
        return str(self.date)

    def get_date(self):
        return self.date

    def set_date(self, value):
        self.date = value

    def get_practices(self):
        return self.practices

    def set_practices(self, value):
        self.practices = value

    def get_request(self):
        return self.request

    def set_request(self, request):
        self.request = request

    def get_season(self):
        return self.season

    def set_season(self, season):
        self.season = season

    def get_mentor(self):
        return self.mentor

    def set_mentor(self, mentor):
        self.mentor = mentor

    def get_pace(self):
        return self.pace

    def set_pace(self, value):
        self.pace = value

    def get_might_come_to_practice(self):
        return self.might_come_to_practice

    def set_might_come_to_practice(self, value):
        self.might_come_to_practice = value

    def get_cant_make_practice(self):
        return self.cant_make_practice

    def set_cant_make_practice(self, value):
        self.cant_make_practice = value

    def get_comments(self):
        return self.comments

    def set_comments(self, value):
        self.comments = value


class PracticeReminderRecipientKind(models.TextChoices):
    STAFF = "staff", "TFK Staff"
    COACH = "coach", "Coach"
    MENTOR = "mentor", "Mentor"


class PracticeReminderKind(models.TextChoices):
    BEFORE_FIRST = "before_first", "Before first practice"
    AFTER_PRACTICE = "after_practice", "After practice"


class PracticeReminderEmail(TimeStampedModel):
    """Reminder email about upcoming practice session(s)."""

    season = models.ForeignKey(
        Season,
        on_delete=models.CASCADE,
        related_name="practice_reminder_emails",
    )
    kind = models.CharField(
        max_length=20,
        choices=PracticeReminderKind.choices,
        default=PracticeReminderKind.AFTER_PRACTICE,
        help_text="Whether this sends before the season's first practice or after an anchor practice.",
    )
    anchor_practice = models.ForeignKey(
        Practice,
        on_delete=models.CASCADE,
        related_name="practice_reminder_emails",
        help_text=(
            "For after-practice reminders, the practice after which this sends. "
            "For before-first reminders, the season's first practice."
        ),
    )
    practice_one = models.ForeignKey(
        Practice,
        on_delete=models.CASCADE,
        related_name="practice_reminders_as_first",
        help_text="First upcoming practice covered in this email.",
    )
    practice_two = models.ForeignKey(
        Practice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="practice_reminders_as_second",
        help_text="Second upcoming practice covered in this email, if any.",
    )
    scheduled_send_at = models.DateTimeField(
        db_index=True,
        null=True,
        blank=True,
        help_text=(
            "When to send automatically. After-practice default: 6:15 AM the morning after "
            "anchor practice. Before-first default: 6:15 AM two days before the first practice. "
            "Null means manual send only (e.g. first practice is less than 48 hours away)."
        ),
    )
    subject = models.TextField(
        help_text=(
            "Subject template. Use {{ date_of_practice_1 }}, {{ date_of_practice_2 }}, "
            "and {{ first_name }} / {{ last_name }} for the recipient."
        ),
    )
    body_text = models.TextField(
        help_text=(
            "Body template. Use {{ first_name }}, {{ last_name }}, {{ year }}, "
            "{{ date_of_practice_1 }}, {{ date_of_practice_2 }}, {{ practice_1_section }}, "
            "{{ practice_2_section }}, {{ mentor_practice_1_notice }}, "
            "{{ mentor_practice_2_notice }}."
        ),
    )
    task_completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the send task finished (null if not run yet).",
    )
    recipients_emailed_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="How many recipients received this email when it was sent.",
    )

    class Meta:
        ordering = [models.F("scheduled_send_at").asc(nulls_last=True), "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["anchor_practice", "kind"],
                name="unique_practice_reminder_anchor_kind",
            )
        ]

    def __str__(self):
        return f"Practice reminder ({self.kind}) anchor {self.anchor_practice_id}"


class PracticeReminderSuppression(TimeStampedModel):
    """User-dismissed reminder that sync should not recreate."""

    season = models.ForeignKey(
        Season,
        on_delete=models.CASCADE,
        related_name="practice_reminder_suppressions",
    )
    anchor_practice = models.ForeignKey(
        Practice,
        on_delete=models.CASCADE,
        related_name="practice_reminder_suppressions",
    )
    kind = models.CharField(
        max_length=20,
        choices=PracticeReminderKind.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["anchor_practice", "kind"],
                name="unique_practice_reminder_suppression",
            )
        ]

    def __str__(self):
        return f"Suppressed {self.kind} reminder for practice {self.anchor_practice_id}"


class PracticeReminderSendRecord(TimeStampedModel):
    """Rendered copy of a practice reminder email sent to one recipient."""

    reminder = models.ForeignKey(
        PracticeReminderEmail,
        on_delete=models.CASCADE,
        related_name="send_records",
    )
    recipient_email = models.EmailField()
    recipient_first_name = models.CharField(max_length=100, blank=True)
    recipient_last_name = models.CharField(max_length=100, blank=True)
    recipient_kind = models.CharField(
        max_length=16,
        choices=PracticeReminderRecipientKind.choices,
    )
    rendered_subject = models.TextField()
    rendered_body = models.TextField()
    sent_at = models.DateTimeField()

    class Meta:
        ordering = ["recipient_last_name", "recipient_first_name", "id"]

    def __str__(self):
        return f"{self.recipient_email} ← reminder {self.reminder_id}"


class ScheduledEmail(TimeStampedModel):
    """Scheduled bulk email to mentors with per-recipient template placeholders."""

    scheduled_send_at = models.DateTimeField(
        db_index=True,
        help_text="Date and time when this email should go out.",
    )
    task_completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the send task finished (null if not run yet).",
    )
    recipients_emailed_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="How many mentors received this email when it was sent.",
    )
    body_text = models.TextField(
        help_text=(
            "Message template. Use {{ first_name }}, {{ last_name }}, {{ year }}, {{ pace }}, "
            "and {{ link }} (personal reply URL); replaced per mentor when the email is sent."
        ),
    )
    practices = models.ManyToManyField(
        Practice,
        related_name="scheduled_emails",
        blank=True,
        help_text="Practices included or referenced in this email.",
    )
    recipient_mode = models.CharField(
        max_length=32,
        choices=ScheduledEmailRecipientMode.choices,
        default=ScheduledEmailRecipientMode.ALL_IN_SEASON,
        help_text="Whether to email every mentor in a season or only selected mentors.",
    )
    recipient_season = models.ForeignKey(
        Season,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_emails_all_mentors",
        help_text="When recipient_mode is all_in_season, every mentor linked to this season is included.",
    )
    specific_mentors = models.ManyToManyField(
        Mentor,
        blank=True,
        related_name="scheduled_emails_explicit",
        help_text="When recipient_mode is specific_mentors, only these mentors receive the email.",
    )

    class Meta:
        ordering = ["-scheduled_send_at", "-id"]

    def __str__(self):
        return f"Scheduled email @ {self.scheduled_send_at}"

    def get_scheduled_send_at(self):
        return self.scheduled_send_at

    def set_scheduled_send_at(self, value):
        self.scheduled_send_at = value

    def get_task_completed_at(self):
        return self.task_completed_at

    def set_task_completed_at(self, value):
        self.task_completed_at = value

    def get_body_text(self):
        return self.body_text

    def set_body_text(self, value):
        self.body_text = value

    def get_practices(self):
        return self.practices.all()

    def set_practices(self, practices):
        self.practices.set(practices)

    def get_recipient_mode(self):
        return self.recipient_mode

    def set_recipient_mode(self, value):
        self.recipient_mode = value

    def get_recipient_season(self):
        return self.recipient_season

    def set_recipient_season(self, season):
        self.recipient_season = season

    def get_specific_mentors(self):
        return self.specific_mentors.all()

    def set_specific_mentors(self, mentors):
        self.specific_mentors.set(mentors)

    def clean(self):
        super().clean()
        if self.recipient_mode in (
            ScheduledEmailRecipientMode.ALL_IN_SEASON,
            ScheduledEmailRecipientMode.ALL_AT_PRACTICE_IN_SEASON,
            ScheduledEmailRecipientMode.ALL_REMOTE_IN_SEASON,
        ):
            if self.recipient_season_id is None:
                raise ValidationError(
                    {
                        "recipient_season": "Select a season when including mentors from that season."
                    }
                )
        elif self.recipient_mode == ScheduledEmailRecipientMode.SPECIFIC_MENTORS:
            if self.pk and not self.specific_mentors.exists():
                raise ValidationError(
                    {
                        "specific_mentors": "Select at least one mentor for specific-mentor sends."
                    }
                )

    def get_target_mentors(self):
        """Mentors who should receive this email when it is sent."""
        if self.recipient_mode == ScheduledEmailRecipientMode.SPECIFIC_MENTORS:
            return (
                Mentor.objects.filter(
                    pk__in=self.specific_mentors.values_list("pk", flat=True)
                )
                .distinct()
                .order_by("last_name", "first_name", "id")
            )
        if not self.recipient_season_id:
            return Mentor.objects.none()
        mentors = Mentor.objects.filter(seasons=self.recipient_season)
        if self.recipient_mode == ScheduledEmailRecipientMode.ALL_AT_PRACTICE_IN_SEASON:
            mentors = mentors.filter(type=MentorTypes.PRACTICE)
        elif self.recipient_mode == ScheduledEmailRecipientMode.ALL_REMOTE_IN_SEASON:
            mentors = mentors.filter(type=MentorTypes.REMOTE)
        return mentors.distinct().order_by("last_name", "first_name", "id")

    def sync_mentor_tokens(self):
        """Create/remove per-mentor reply tokens to match current recipient list."""
        if self.task_completed_at:
            return
        mentor_ids = list(self.get_target_mentors().values_list("pk", flat=True))
        for mid in mentor_ids:
            ScheduledEmailMentorToken.objects.get_or_create(
                scheduled_email=self,
                mentor_id=mid,
            )
        self.mentor_tokens.exclude(mentor_id__in=mentor_ids).delete()

    def mark_sent_recipients(self, mentor_ids=None):
        """Record which mentors received this email when it was sent."""
        if mentor_ids is None:
            mentor_ids = list(
                self.get_target_mentors().values_list("pk", flat=True)
            )
        self.mentor_tokens.filter(mentor_id__in=mentor_ids).update(
            included_in_send=True
        )
        count = self.mentor_tokens.filter(included_in_send=True).count()
        self.recipients_emailed_count = count
        return count

    def ensure_mentor_tokens_for_stats(self):
        """Create missing reply tokens without removing existing ones (safe for stats reads)."""
        if self.task_completed_at:
            return
        mentor_ids = set(self.mentor_tokens.values_list("mentor_id", flat=True))
        mentor_ids.update(
            ScheduledEmailMentorPracticeReply.objects.filter(
                mentor_token__scheduled_email_id=self.pk,
            ).values_list("mentor_id", flat=True)
        )
        mentor_ids.update(
            self.get_target_mentors().values_list("pk", flat=True)
        )
        for mid in mentor_ids:
            ScheduledEmailMentorToken.objects.get_or_create(
                scheduled_email=self,
                mentor_id=mid,
            )

    def _send_time_mentor_token_queryset(self):
        """Tokens issued on or before this email was sent."""
        if not self.task_completed_at:
            return self.mentor_tokens.all()
        cutoff = self.task_completed_at + timedelta(minutes=1)
        return self.mentor_tokens.filter(created_at__lte=cutoff)

    def _emailed_mentor_ids_for_stats(self):
        email_id = self.pk
        if self.task_completed_at:
            mentor_ids = set(
                ScheduledEmailMentorToken.objects.filter(
                    scheduled_email_id=email_id,
                    included_in_send=True,
                ).values_list("mentor_id", flat=True)
            )
            mentor_ids.update(
                ScheduledEmailMentorPracticeReply.objects.filter(
                    mentor_token__scheduled_email_id=email_id,
                ).values_list("mentor_id", flat=True)
            )
            if not mentor_ids:
                mentor_ids = set(
                    self._send_time_mentor_token_queryset().values_list(
                        "mentor_id", flat=True
                    )
                )
            return mentor_ids

        mentor_ids = set(
            ScheduledEmailMentorToken.objects.filter(
                scheduled_email_id=email_id
            ).values_list("mentor_id", flat=True)
        )
        mentor_ids.update(
            ScheduledEmailMentorPracticeReply.objects.filter(
                mentor_token__scheduled_email_id=email_id,
            ).values_list("mentor_id", flat=True)
        )
        if not mentor_ids:
            mentor_ids = set(
                self.get_target_mentors().values_list("pk", flat=True)
            )
        if not mentor_ids:
            mentor_ids = set(
                self.specific_mentors.values_list("pk", flat=True)
            )
        return mentor_ids

    def _mentors_replied_ids_for_stats(self, emailed_mentor_ids):
        """Mentors who submitted a reply (or confirmed receipt) for this send."""
        if not emailed_mentor_ids:
            return set()
        email_id = self.pk
        replied_ids = set(
            ScheduledEmailMentorPracticeReply.objects.filter(
                mentor_token__scheduled_email_id=email_id,
                mentor_id__in=emailed_mentor_ids,
            ).values_list("mentor_id", flat=True)
        )
        replied_ids.update(
            ScheduledEmailMentorToken.objects.filter(
                scheduled_email_id=email_id,
                mentor_id__in=emailed_mentor_ids,
                email_received_confirmed=True,
            ).values_list("mentor_id", flat=True)
        )
        return replied_ids

    def _pending_mentor_ids_for_stats(self, emailed_mentor_ids):
        """Mentors still awaiting a reply for this send."""
        replied_ids = self._mentors_replied_ids_for_stats(emailed_mentor_ids)
        return emailed_mentor_ids - replied_ids

    def query_pending_mentors(self):
        """Mentors who were emailed but have not yet replied."""
        self.ensure_mentor_tokens_for_stats()
        emailed_mentor_ids = self._emailed_mentor_ids_for_stats()
        pending_ids = self._pending_mentor_ids_for_stats(
            emailed_mentor_ids
        )
        return Mentor.objects.filter(pk__in=pending_ids).order_by(
            "last_name", "first_name", "id"
        )

    def pending_mentors(self):
        """Alias kept for callers expecting ``pending_mentors()``."""
        return self.query_pending_mentors()

    def pending_mentors_for_reminder(self):
        """Pending mentors with an email address (can receive reminders)."""
        return self.query_pending_mentors().exclude(email="")

    @staticmethod
    def serialize_pending_mentor_rows(mentors):
        return [
            {
                "id": mentor.id,
                "first_name": mentor.first_name,
                "last_name": mentor.last_name,
                "name": f"{mentor.first_name} {mentor.last_name}".strip(),
                "email": mentor.email,
                "type": mentor.type,
            }
            for mentor in mentors
        ]

    def reply_stats(self):
        """Mentors emailed vs reply-page submissions and practice selections."""
        self.ensure_mentor_tokens_for_stats()
        attending_values = {
            PracticeAttendanceReply.ATTENDING,
            PracticeAttendanceReply.FIRST_HALF,
            PracticeAttendanceReply.SECOND_HALF,
        }
        emailed_mentor_ids = self._emailed_mentor_ids_for_stats()
        mentors_emailed = len(emailed_mentor_ids)

        mentors_replied_ids = self._mentors_replied_ids_for_stats(
            emailed_mentor_ids
        )
        mentors_replied = len(mentors_replied_ids)
        pending_ids = self._pending_mentor_ids_for_stats(emailed_mentor_ids)

        selected_ids = set(
            ScheduledEmailMentorPracticeReply.objects.filter(
                mentor_token__scheduled_email_id=self.pk,
                mentor_id__in=emailed_mentor_ids,
                attendance__in=attending_values,
            ).values_list("mentor_id", flat=True)
        )

        pending_mentors = list(
            Mentor.objects.filter(pk__in=pending_ids).order_by(
                "last_name", "first_name", "id"
            )
        )

        return {
            "mentors_emailed": mentors_emailed,
            "mentors_replied": mentors_replied,
            "mentors_selected_practices": len(selected_ids),
            "mentors_responded": mentors_replied,
            "mentors_pending": max(0, len(pending_ids)),
            "pending_mentor_ids": sorted(pending_ids),
            "pending_mentors": self.serialize_pending_mentor_rows(pending_mentors),
        }

    def reply_stats_summary(self):
        """Count-only reply stats for list views (no token writes, no mentor rows)."""
        return self.reply_stats_summaries_for([self])[self.pk]

    @classmethod
    def reply_stats_summaries_for(cls, emails):
        """Bulk count-only reply stats keyed by scheduled email id.

        Uses prefetched ``mentor_tokens`` when present, plus one practice-reply
        query for the whole page.
        """
        emails = [email for email in emails if email is not None and email.pk]
        if not emails:
            return {}

        attending_values = {
            PracticeAttendanceReply.ATTENDING,
            PracticeAttendanceReply.FIRST_HALF,
            PracticeAttendanceReply.SECOND_HALF,
        }
        email_ids = [email.pk for email in emails]
        tokens_by_email = {email.pk: [] for email in emails}
        missing_token_email_ids = []

        for email in emails:
            cache = getattr(email, "_prefetched_objects_cache", None) or {}
            if "mentor_tokens" in cache:
                tokens_by_email[email.pk] = list(email.mentor_tokens.all())
            else:
                missing_token_email_ids.append(email.pk)

        if missing_token_email_ids:
            for token in ScheduledEmailMentorToken.objects.filter(
                scheduled_email_id__in=missing_token_email_ids
            ):
                tokens_by_email[token.scheduled_email_id].append(token)

        replies_by_email = {email_id: [] for email_id in email_ids}
        for row in ScheduledEmailMentorPracticeReply.objects.filter(
            mentor_token__scheduled_email_id__in=email_ids
        ).values("mentor_token__scheduled_email_id", "mentor_id", "attendance"):
            replies_by_email[row["mentor_token__scheduled_email_id"]].append(row)

        summaries = {}
        for email in emails:
            summaries[email.pk] = cls._reply_stats_summary_from_rows(
                email,
                tokens_by_email.get(email.pk, []),
                replies_by_email.get(email.pk, []),
                attending_values,
            )
        return summaries

    @classmethod
    def _reply_stats_summary_from_rows(
        cls, email, tokens, reply_rows, attending_values
    ):
        reply_mentor_ids = {row["mentor_id"] for row in reply_rows}

        if email.task_completed_at:
            emailed_mentor_ids = {
                token.mentor_id for token in tokens if token.included_in_send
            }
            emailed_mentor_ids.update(reply_mentor_ids)
            if not emailed_mentor_ids:
                cutoff = email.task_completed_at + timedelta(minutes=1)
                emailed_mentor_ids = {
                    token.mentor_id
                    for token in tokens
                    if token.created_at <= cutoff
                }
        else:
            emailed_mentor_ids = {token.mentor_id for token in tokens}
            emailed_mentor_ids.update(reply_mentor_ids)
            if not emailed_mentor_ids:
                specific_cache = getattr(email, "_prefetched_objects_cache", None) or {}
                if "specific_mentors" in specific_cache:
                    emailed_mentor_ids = {
                        mentor.pk for mentor in email.specific_mentors.all()
                    }
                if not emailed_mentor_ids:
                    emailed_mentor_ids = set(
                        email.get_target_mentors().values_list("pk", flat=True)
                    )
                if not emailed_mentor_ids:
                    emailed_mentor_ids = set(
                        email.specific_mentors.values_list("pk", flat=True)
                    )

        if not emailed_mentor_ids:
            return {
                "mentors_emailed": 0,
                "mentors_replied": 0,
                "mentors_selected_practices": 0,
                "mentors_responded": 0,
                "mentors_pending": 0,
                "pending_mentor_ids": [],
            }

        replied_ids = {
            row["mentor_id"]
            for row in reply_rows
            if row["mentor_id"] in emailed_mentor_ids
        }
        replied_ids.update(
            token.mentor_id
            for token in tokens
            if token.email_received_confirmed
            and token.mentor_id in emailed_mentor_ids
        )
        selected_ids = {
            row["mentor_id"]
            for row in reply_rows
            if row["mentor_id"] in emailed_mentor_ids
            and row["attendance"] in attending_values
        }
        pending_ids = emailed_mentor_ids - replied_ids
        mentors_replied = len(replied_ids)
        return {
            "mentors_emailed": len(emailed_mentor_ids),
            "mentors_replied": mentors_replied,
            "mentors_selected_practices": len(selected_ids),
            "mentors_responded": mentors_replied,
            "mentors_pending": max(0, len(pending_ids)),
            "pending_mentor_ids": sorted(pending_ids),
        }

    def reply_absolute_url_for_mentor(self, mentor):
        """Public mentor reply URL including opaque token (requires sync_mentor_tokens first)."""
        mentor_id = getattr(mentor, "pk", None) or mentor
        mt, _ = ScheduledEmailMentorToken.objects.get_or_create(
            scheduled_email=self,
            mentor_id=mentor_id,
        )
        base = getattr(settings, "FRONTEND_PUBLIC_URL", "http://localhost:5173").rstrip(
            "/"
        )
        return f"{base}/mentor-reply?token={mt.token}"

    def resolve_season_year(self):
        """Season year for {{ year }} from recipient_season or linked practices."""
        if self.recipient_season_id:
            return self.recipient_season.year
        practice = self.practices.select_related("season").order_by("date").first()
        if practice:
            return practice.season.year
        return None

    def resolve_pace_for_mentor(self, mentor):
        """Pace from MentorPracticeAssignment on linked practices, else mentor default."""
        practice_ids = list(self.practices.values_list("pk", flat=True))
        if not practice_ids:
            return mentor.pace
        assignment = (
            MentorPracticeAssignment.objects.filter(
                mentor=mentor, practice_id__in=practice_ids
            )
            .select_related("practice")
            .order_by("practice__date", "id")
            .first()
        )
        if assignment:
            return assignment.pace
        return mentor.pace

    def render_body_for_mentor(self, mentor):
        """Replace template placeholders with this mentor's values (plain text)."""
        pace = self.resolve_pace_for_mentor(mentor)
        link = self.reply_absolute_url_for_mentor(mentor)
        year = self.resolve_season_year()

        def repl(match):
            key = match.group(1).lower()
            if key == "first_name":
                return mentor.first_name or ""
            if key == "last_name":
                return mentor.last_name or ""
            if key == "year":
                return str(year) if year is not None else ""
            if key == "pace":
                return str(pace or "")
            if key == "link":
                return link
            return match.group(0)

        return EMAIL_TEMPLATE_PLACEHOLDER_RE.sub(repl, self.body_text)

    def render_reminder_body_for_mentor(self, mentor):
        """Plain-text reminder for mentors who have not yet replied."""
        link = self.reply_absolute_url_for_mentor(mentor)
        year = self.resolve_season_year()
        lines = [
            f"Hi {mentor.first_name},",
            "",
        ]
        if year:
            lines.append(
                f"This is a reminder about mentor practice availability "
                f"for the {year} NYC Marathon season."
            )
        else:
            lines.append(
                "This is a reminder about mentor practice availability."
            )
        lines.extend(
            [
                "",
                "At Practice mentors must reply with their availability.",
                "",
                "Please use your personal link below to confirm which practices "
                "you can attend:",
                link,
                "",
                "Thanks,",
                "Your friendly Mentor Coordinator Ted",
            ]
        )
        return "\n".join(lines)


class ScheduledEmailMentorToken(TimeStampedModel):
    """Opaque token embedded in {{ link }} so a mentor can open their reply page."""

    scheduled_email = models.ForeignKey(
        ScheduledEmail,
        on_delete=models.CASCADE,
        related_name="mentor_tokens",
    )
    mentor = models.ForeignKey(
        Mentor,
        on_delete=models.CASCADE,
        related_name="scheduled_email_tokens",
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email_received_confirmed = models.BooleanField(default=False)
    included_in_send = models.BooleanField(
        default=False,
        help_text="True when this mentor was emailed as part of the send.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scheduled_email", "mentor"],
                name="unique_scheduled_email_mentor_token",
            )
        ]

    def __str__(self):
        return f"{self.scheduled_email_id} → mentor {self.mentor_id}"


class ScheduledEmailMentorPracticeReply(TimeStampedModel):
    """One mentor's availability answer for a practice on a scheduled email."""

    mentor_token = models.ForeignKey(
        ScheduledEmailMentorToken,
        on_delete=models.CASCADE,
        related_name="practice_replies",
    )
    mentor = models.ForeignKey(
        Mentor,
        on_delete=models.CASCADE,
        related_name="scheduled_email_practice_replies",
    )
    practice = models.ForeignKey(
        Practice,
        on_delete=models.CASCADE,
        related_name="mentor_email_replies",
    )
    attendance = models.CharField(max_length=20, choices=PracticeAttendanceReply.choices)
    pace = models.CharField(
        max_length=11,
        choices=PaceTypes.choices,
        blank=True,
        default="",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["mentor_token", "practice"],
                name="unique_mentor_token_practice_reply",
            )
        ]

    def save(self, *args, **kwargs):
        if self.pace:
            self.pace = normalize_pace(self.pace)
        super().save(*args, **kwargs)


class MentorCellPhoneRequestSend(TimeStampedModel):
    """One batch of cell-phone request emails to assigned mentors missing a number."""

    season = models.ForeignKey(
        Season,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mentor_cell_phone_request_sends",
    )
    sent_at = models.DateTimeField(db_index=True)
    recipients_emailed_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-sent_at", "-id"]

    def __str__(self):
        return f"Cell phone request send {self.id} ({self.recipients_emailed_count})"


class MentorCellPhoneRequestToken(TimeStampedModel):
    """One-time personal link from a cell-phone request email for one mentor."""

    send = models.ForeignKey(
        MentorCellPhoneRequestSend,
        on_delete=models.CASCADE,
        related_name="tokens",
    )
    mentor = models.ForeignKey(
        Mentor,
        on_delete=models.CASCADE,
        related_name="cell_phone_request_tokens",
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["send", "mentor"],
                name="unique_cell_phone_request_send_mentor",
            )
        ]

    def __str__(self):
        return f"Cell phone token {self.token} → mentor {self.mentor_id}"

    @property
    def is_usable(self):
        return self.used_at is None and self.sent_at is not None

    def absolute_url(self):
        base = getattr(settings, "FRONTEND_PUBLIC_URL", "http://localhost:5173").rstrip(
            "/"
        )
        return f"{base}/mentor-cell-phone?token={self.token}"

