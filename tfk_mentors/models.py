import re
import uuid

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
    SPECIFIC_MENTORS = "specific_mentors", "Specific mentors"


class PracticeAttendanceReply(models.TextChoices):
    ATTENDING = "attending", "Attending"
    NOT_ATTENDING = "not_attending", "Not attending"
    FIRST_HALF = "first_half", "First half"
    SECOND_HALF = "second_half", "Second half"


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

    def __str__(self):
        return str(self.year)

    def get_year(self):
        return self.year

    def set_year(self, value):
        self.year = value


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


class Mentor(TimeStampedModel):
    """Model for an item with timestamps."""

    first_name = models.CharField(max_length=75)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=100, unique=True)
    cell_phone = models.CharField(max_length=20)
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
    mentors = models.ManyToManyField(Mentor)
    full_practice = models.BooleanField(default=True)
    season = models.ForeignKey(Season, on_delete=models.CASCADE)

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

    def get_full_practice(self):
        return self.full_practice

    def set_full_practice(self, value):
        self.full_practice = value

    def get_season(self):
        return self.season

    def set_season(self, season):
        self.season = season

    def get_mentors(self):
        return self.mentors.all()

    def set_mentors(self, mentors):
        self.mentors.set(mentors)

    def latest_attending_mentor_replies(self):
        """Latest attending reply per mentor linked via ScheduledEmailMentorPracticeReply."""
        attending_values = (
            PracticeAttendanceReply.ATTENDING,
            PracticeAttendanceReply.FIRST_HALF,
            PracticeAttendanceReply.SECOND_HALF,
        )
        replies = (
            self.mentor_email_replies.filter(attendance__in=attending_values)
            .select_related("mentor", "mentor_token__scheduled_email")
            .order_by("-updated_at")
        )
        latest_by_mentor = {}
        for reply in replies:
            if reply.mentor_id not in latest_by_mentor:
                latest_by_mentor[reply.mentor_id] = reply
        return sorted(
            latest_by_mentor.values(),
            key=lambda reply: (reply.mentor.last_name, reply.mentor.first_name),
        )

    def sync_mentor_assignments_from_replies(self):
        """Align MentorPracticeAssignment + practice.mentors with reply attendance."""
        attending_replies = self.latest_attending_mentor_replies()
        attending_mentor_ids = [reply.mentor_id for reply in attending_replies]

        MentorPracticeAssignment.objects.filter(practice=self).exclude(
            mentor_id__in=attending_mentor_ids
        ).delete()

        for reply in attending_replies:
            pace = normalize_pace(reply.pace or reply.mentor.pace or "")
            MentorPracticeAssignment.objects.update_or_create(
                mentor_id=reply.mentor_id,
                practice=self,
                defaults={"pace": pace},
            )

        self.mentors.set(attending_mentor_ids)

    def get_or_create_mentor_reply_token(self, mentor):
        """Token for storing admin or mentor replies tied to this practice."""
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
    pace = models.CharField(choices=PaceTypes, max_length=11)

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
        if self.recipient_mode == ScheduledEmailRecipientMode.ALL_IN_SEASON:
            if self.recipient_season_id is None:
                raise ValidationError(
                    {
                        "recipient_season": "Select a season when including all mentors in that season."
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
        return (
            Mentor.objects.filter(seasons=self.recipient_season)
            .distinct()
            .order_by("last_name", "first_name", "id")
        )

    def sync_mentor_tokens(self):
        """Create/remove per-mentor reply tokens to match current recipient list."""
        mentor_ids = list(self.get_target_mentors().values_list("pk", flat=True))
        for mid in mentor_ids:
            ScheduledEmailMentorToken.objects.get_or_create(
                scheduled_email=self,
                mentor_id=mid,
            )
        self.mentor_tokens.exclude(mentor_id__in=mentor_ids).delete()

    def ensure_mentor_tokens_for_stats(self):
        """Create missing reply tokens without removing existing ones (safe for stats reads)."""
        mentor_ids = set(self.get_target_mentors().values_list("pk", flat=True))
        mentor_ids.update(self.mentor_tokens.values_list("mentor_id", flat=True))
        mentor_ids.update(
            ScheduledEmailMentorPracticeReply.objects.filter(
                mentor_token__scheduled_email_id=self.pk,
            ).values_list("mentor_id", flat=True)
        )
        for mid in mentor_ids:
            ScheduledEmailMentorToken.objects.get_or_create(
                scheduled_email=self,
                mentor_id=mid,
            )

    def _emailed_mentor_ids_for_stats(self):
        email_id = self.pk
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

    def _linked_practice_ids_for_stats(self, emailed_mentor_ids):
        """Practices tied to this send: linked on the email plus reply targets."""
        email_id = self.pk
        practice_ids = set(
            Practice.objects.filter(scheduled_emails__pk=email_id).values_list(
                "pk", flat=True
            )
        )
        practice_ids.update(
            ScheduledEmailMentorPracticeReply.objects.filter(
                mentor_token__scheduled_email_id=email_id,
            ).values_list("practice_id", flat=True)
        )
        if not practice_ids and emailed_mentor_ids:
            practice_ids.update(
                ScheduledEmailMentorPracticeReply.objects.filter(
                    mentor_id__in=emailed_mentor_ids,
                ).values_list("practice_id", flat=True)
            )
        if (
            not practice_ids
            and self.recipient_season_id
            and emailed_mentor_ids
        ):
            practice_ids.update(
                Practice.objects.filter(season_id=self.recipient_season_id)
                .filter(
                    models.Q(
                        mentor_email_replies__mentor_id__in=emailed_mentor_ids
                    )
                    | models.Q(
                        mentorpracticeassignment__mentor_id__in=emailed_mentor_ids
                    )
                )
                .values_list("pk", flat=True)
                .distinct()
            )
        return practice_ids

    def _mentors_replied_ids_for_stats(self, emailed_mentor_ids, practice_ids):
        email_id = self.pk
        replied_ids = set(
            ScheduledEmailMentorPracticeReply.objects.filter(
                mentor_token__scheduled_email_id=email_id,
            ).values_list("mentor_id", flat=True)
        )
        replied_ids.update(
            ScheduledEmailMentorToken.objects.filter(
                scheduled_email_id=email_id,
                email_received_confirmed=True,
            ).values_list("mentor_id", flat=True)
        )

        if practice_ids and emailed_mentor_ids:
            replied_ids.update(
                ScheduledEmailMentorPracticeReply.objects.filter(
                    practice_id__in=practice_ids,
                    mentor_id__in=emailed_mentor_ids,
                ).values_list("mentor_id", flat=True)
            )
            replied_ids.update(
                MentorPracticeAssignment.objects.filter(
                    practice_id__in=practice_ids,
                    mentor_id__in=emailed_mentor_ids,
                ).values_list("mentor_id", flat=True)
            )

        return replied_ids

    def pending_mentors(self):
        """Mentors who were emailed but have not yet replied."""
        self.ensure_mentor_tokens_for_stats()
        emailed_mentor_ids = self._emailed_mentor_ids_for_stats()
        practice_ids = self._linked_practice_ids_for_stats(emailed_mentor_ids)
        replied_ids = self._mentors_replied_ids_for_stats(
            emailed_mentor_ids, practice_ids
        )
        pending_ids = emailed_mentor_ids - replied_ids
        return Mentor.objects.filter(pk__in=pending_ids).order_by(
            "last_name", "first_name", "id"
        )

    def pending_mentors_for_reminder(self):
        """Pending mentors with an email address (can receive reminders)."""
        return self.pending_mentors().exclude(email="")

    def reply_stats(self):
        """Mentors emailed vs reply-page submissions and practice selections."""
        attending_values = {
            PracticeAttendanceReply.ATTENDING,
            PracticeAttendanceReply.FIRST_HALF,
            PracticeAttendanceReply.SECOND_HALF,
        }
        emailed_mentor_ids = self._emailed_mentor_ids_for_stats()
        mentors_emailed = len(emailed_mentor_ids)
        practice_ids = self._linked_practice_ids_for_stats(emailed_mentor_ids)

        mentors_replied_ids = self._mentors_replied_ids_for_stats(
            emailed_mentor_ids, practice_ids
        )
        mentors_replied = len(mentors_replied_ids)

        selected_ids = set(
            ScheduledEmailMentorPracticeReply.objects.filter(
                mentor_token__scheduled_email_id=self.pk,
                attendance__in=attending_values,
            ).values_list("mentor_id", flat=True)
        )
        if practice_ids and emailed_mentor_ids:
            selected_ids.update(
                ScheduledEmailMentorPracticeReply.objects.filter(
                    practice_id__in=practice_ids,
                    mentor_id__in=emailed_mentor_ids,
                    attendance__in=attending_values,
                ).values_list("mentor_id", flat=True)
            )
        if not selected_ids and mentors_replied_ids and practice_ids:
            selected_ids = set(
                MentorPracticeAssignment.objects.filter(
                    practice_id__in=practice_ids,
                    mentor_id__in=mentors_replied_ids,
                ).values_list("mentor_id", flat=True)
            )

        return {
            "mentors_emailed": mentors_emailed,
            "mentors_replied": mentors_replied,
            "mentors_selected_practices": len(selected_ids),
            "mentors_responded": mentors_replied,
            "mentors_pending": max(0, mentors_emailed - mentors_replied),
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
