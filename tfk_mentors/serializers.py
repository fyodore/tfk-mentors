from django.db.models import Prefetch
from rest_framework import serializers

from .models import (
    Coach,
    CoachPracticeAssignment,
    Mentor,
    MentorPracticeAssignment,
    MentorPracticeShowUp,
    MentorTypes,
    PaceTypes,
    PACE_SORT,
    Practice,
    PracticeAttendanceReply,
    PracticeReminderEmail,
    PracticeReminderKind,
    PracticeReminderSendRecord,
    Requests,
    ScheduledEmail,
    ScheduledEmailRecipientMode,
    Season,
    ShowUpStatus,
    TfkStaff,
    normalize_pace,
)


class SeasonSerializer(serializers.ModelSerializer):
    head_coach = serializers.PrimaryKeyRelatedField(
        queryset=Coach.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Season
        fields = [
            "id",
            "year",
            "is_current",
            "head_coach",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_head_coach(self, value):
        if value is None:
            return value
        season = self.instance
        if season is None:
            return value
        if not value.seasons.filter(id=season.id).exists():
            raise serializers.ValidationError(
                "Head coach must belong to this season."
            )
        return value

    def _clear_other_current_seasons(self, keep_id):
        Season.objects.filter(is_current=True).exclude(pk=keep_id).update(
            is_current=False
        )

    def create(self, validated_data):
        if validated_data.get("is_current"):
            self._clear_other_current_seasons(None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if validated_data.get("is_current"):
            self._clear_other_current_seasons(instance.pk)
        return super().update(instance, validated_data)


class CoachSerializer(serializers.ModelSerializer):
    seasons = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Season.objects.all(), required=False
    )
    cell = serializers.CharField(max_length=20, allow_blank=True, required=False)

    class Meta:
        model = Coach
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "cell",
            "seasons",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TfkStaffSerializer(serializers.ModelSerializer):
    cell_phone = serializers.CharField(max_length=20, allow_blank=True, required=False)

    class Meta:
        model = TfkStaff
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "cell_phone",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class MentorSerializer(serializers.ModelSerializer):
    seasons = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Season.objects.all(), required=False
    )

    class Meta:
        model = Mentor
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "cell_phone",
            "type",
            "pace",
            "split_practice",
            "seasons",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_pace(self, value):
        if not (value or "").strip():
            return ""
        normalized = normalize_pace(value)
        valid = {choice.value for choice in PaceTypes}
        if normalized not in valid:
            raise serializers.ValidationError(f'"{value}" is not a valid choice.')
        return normalized

    def validate(self, attrs):
        mentor_type = attrs.get(
            "type",
            getattr(self.instance, "type", None) if self.instance else None,
        )
        pace = attrs.get(
            "pace",
            getattr(self.instance, "pace", "") if self.instance else "",
        )
        if mentor_type == MentorTypes.REMOTE:
            attrs["pace"] = pace or ""
            attrs["cell_phone"] = (attrs.get("cell_phone") or "").strip()
        else:
            if not (pace or "").strip():
                raise serializers.ValidationError(
                    {"pace": "Pace is required for At Practice mentors."}
                )
            cell_phone = attrs.get(
                "cell_phone",
                getattr(self.instance, "cell_phone", "") if self.instance else "",
            )
            if not (cell_phone or "").strip():
                raise serializers.ValidationError(
                    {"cell_phone": "Cell phone is required for At Practice mentors."}
                )
        return attrs


def practice_mentor_reply_payload(reply):
    """Serialized mentor attendance reply for admin practice view."""
    mentor = reply.mentor
    scheduled = reply.mentor_token.scheduled_email
    return {
        "id": reply.id,
        "mentor_id": mentor.id,
        "first_name": mentor.first_name,
        "last_name": mentor.last_name,
        "mentor_type": mentor.type,
        "attendance": reply.attendance,
        "pace": normalize_pace(reply.pace or mentor.pace or ""),
        "responded_at": reply.updated_at.isoformat(),
        "scheduled_email_id": scheduled.id,
        "scheduled_send_at": (
            scheduled.scheduled_send_at.isoformat()
            if scheduled.scheduled_send_at
            else None
        ),
    }


def practice_mentor_assignment_payload(assignment):
    """Serialized direct mentor assignment for admin practice view."""
    mentor = assignment.mentor
    attendance = (
        PracticeAttendanceReply.AVAILABLE
        if assignment.is_available
        else PracticeAttendanceReply.ATTENDING
    )
    return {
        "id": None,
        "mentor_id": mentor.id,
        "first_name": mentor.first_name,
        "last_name": mentor.last_name,
        "mentor_type": mentor.type,
        "attendance": attendance,
        "pace": normalize_pace(assignment.pace or mentor.pace or ""),
        "responded_at": assignment.updated_at.isoformat(),
        "scheduled_email_id": None,
        "scheduled_send_at": None,
    }


def practice_available_mentor_payloads(practice):
    """Available mentors from email replies and direct assignments."""
    payloads = []
    seen = set()
    for reply in practice.latest_available_mentor_replies():
        payloads.append(practice_mentor_reply_payload(reply))
        seen.add(reply.mentor_id)
    for assignment in MentorPracticeAssignment.objects.filter(
        practice=practice,
        is_available=True,
    ).select_related("mentor"):
        if assignment.mentor_id in seen:
            continue
        payloads.append(practice_mentor_assignment_payload(assignment))
        seen.add(assignment.mentor_id)
    return payloads


def practice_attending_mentor_payloads(practice):
    """Attending mentors from email replies and direct assignments."""
    payloads = []
    for _mentor, _pace, reply, assignment in practice.attending_mentor_roster_entries():
        if reply is not None:
            payloads.append(practice_mentor_reply_payload(reply))
        else:
            payloads.append(practice_mentor_assignment_payload(assignment))
    return payloads


def mentor_status_for_practice(mentor, practice):
    """Return assignment status for one mentor on one practice."""
    mentor_id = mentor.id
    for entry_mentor, pace, reply, _assignment in practice.attending_mentor_roster_entries():
        if entry_mentor.id != mentor_id:
            continue
        attendance = (
            reply.attendance
            if reply is not None
            else PracticeAttendanceReply.ATTENDING
        )
        return {
            "status": "assigned",
            "pace": pace,
            "attendance": attendance,
        }

    for reply in practice.latest_available_mentor_replies():
        if reply.mentor_id != mentor_id:
            continue
        return {
            "status": "available",
            "pace": normalize_pace(reply.pace or mentor.pace or ""),
            "attendance": PracticeAttendanceReply.AVAILABLE,
        }

    for assignment in practice.mentorpracticeassignment_set.all():
        if assignment.mentor_id != mentor_id or not assignment.is_available:
            continue
        return {
            "status": "available",
            "pace": normalize_pace(assignment.pace or mentor.pace or ""),
            "attendance": PracticeAttendanceReply.AVAILABLE,
        }

    return {"status": None, "pace": "", "attendance": None}


def build_mentor_practice_rows(mentor, *, show_to_mentors_only=False):
    """All practices in the mentor's seasons with assignment status."""
    season_ids = list(mentor.seasons.values_list("id", flat=True))
    if not season_ids:
        return []

    practices = Practice.objects.filter(season_id__in=season_ids)
    if show_to_mentors_only:
        practices = practices.filter(show_to_mentors=True)
    practices = (
        practices.select_related("season")
        .prefetch_related(
            "mentor_email_replies__mentor",
            "mentor_email_replies__mentor_token__scheduled_email",
            Prefetch(
                "mentorpracticeassignment_set",
                queryset=MentorPracticeAssignment.objects.select_related("mentor"),
            ),
        )
        .order_by("date", "id")
    )

    rows = []
    for practice in practices:
        detail = mentor_status_for_practice(mentor, practice)
        rows.append(
            {
                "practice_id": practice.id,
                "date": practice.date.isoformat(),
                "season_id": practice.season_id,
                "season_year": practice.season.year,
                "nyrr_race": practice.nyrr_race or "",
                "full_practice": practice.full_practice,
                **detail,
            }
        )
    return rows


def build_public_mentor_directory():
    """Mentor summaries for the public directory (practices loaded on expand)."""
    mentors = list(
        Mentor.objects.all()
        .prefetch_related("seasons")
        .order_by("last_name", "first_name", "id")
    )
    mentor_season_ids = {
        mentor.id: {season.id for season in mentor.seasons.all()} for mentor in mentors
    }
    counts = {
        mentor.id: {"assigned_count": 0, "available_count": 0} for mentor in mentors
    }

    season_ids = set()
    for ids in mentor_season_ids.values():
        season_ids.update(ids)

    if season_ids:
        practices = (
            Practice.objects.filter(season_id__in=season_ids, show_to_mentors=True)
            .prefetch_related(
                "mentor_email_replies__mentor",
                "mentor_email_replies__mentor_token__scheduled_email",
                Prefetch(
                    "mentorpracticeassignment_set",
                    queryset=MentorPracticeAssignment.objects.select_related("mentor"),
                ),
            )
            .order_by("date", "id")
        )
        for practice in practices:
            relevant_mentor_ids = [
                mentor_id
                for mentor_id, mentor_seasons in mentor_season_ids.items()
                if practice.season_id in mentor_seasons
            ]
            if not relevant_mentor_ids:
                continue

            attending_ids = {
                mentor.id
                for mentor, _pace, _reply, _assignment in practice.attending_mentor_roster_entries()
            }
            available_ids = set()
            for reply in practice.latest_available_mentor_replies():
                if reply.mentor_id not in attending_ids:
                    available_ids.add(reply.mentor_id)

            latest_by_mentor = practice._latest_reply_by_mentor()
            for assignment in practice.mentorpracticeassignment_set.all():
                if not assignment.is_available or assignment.mentor_id in attending_ids:
                    continue
                latest = latest_by_mentor.get(assignment.mentor_id)
                if (
                    latest is not None
                    and latest.attendance != PracticeAttendanceReply.AVAILABLE
                ):
                    continue
                available_ids.add(assignment.mentor_id)

            for mentor_id in relevant_mentor_ids:
                if mentor_id in attending_ids:
                    counts[mentor_id]["assigned_count"] += 1
                elif mentor_id in available_ids:
                    counts[mentor_id]["available_count"] += 1

    return [
        {
            "id": mentor.id,
            "first_name": mentor.first_name,
            "last_name": mentor.last_name,
            "type": mentor.type,
            "pace": normalize_pace(mentor.pace or ""),
            "assigned_count": counts[mentor.id]["assigned_count"],
            "available_count": counts[mentor.id]["available_count"],
        }
        for mentor in mentors
    ]


def build_public_mentor_directory_practices(mentor):
    """Assigned and available practices for one mentor."""
    assigned_practices = []
    available_practices = []
    for row in build_mentor_practice_rows(mentor, show_to_mentors_only=True):
        if row.get("status") not in {"assigned", "available"}:
            continue
        practice_row = {
            "practice_id": row["practice_id"],
            "date": row["date"],
            "season_year": row["season_year"],
            "nyrr_race": row["nyrr_race"],
            "full_practice": row["full_practice"],
            "pace": row.get("pace") or "",
            "attendance": row.get("attendance"),
        }
        if row["status"] == "assigned":
            assigned_practices.append(practice_row)
        else:
            available_practices.append(practice_row)

    return {
        "mentor_id": mentor.id,
        "assigned_practices": assigned_practices,
        "available_practices": available_practices,
    }


def _public_mentor_roster_row(payload):
    return {
        "mentor_id": payload["mentor_id"],
        "first_name": payload["first_name"],
        "last_name": payload["last_name"],
        "pace": payload["pace"],
        "attendance": payload.get("attendance"),
    }


def _sort_public_mentor_roster_rows(rows):
    return sorted(
        rows,
        key=lambda row: (
            PACE_SORT.get(normalize_pace(row.get("pace") or ""), 99),
            row.get("last_name") or "",
            row.get("first_name") or "",
        ),
    )


def build_public_practice_mentor_roster(practice):
    """Attending and available mentors for one practice (public, no contact info)."""
    practice.sync_mentor_assignments_from_replies()
    attending = _sort_public_mentor_roster_rows(
        _public_mentor_roster_row(payload)
        for payload in practice_attending_mentor_payloads(practice)
    )
    available = _sort_public_mentor_roster_rows(
        _public_mentor_roster_row(payload)
        for payload in practice_available_mentor_payloads(practice)
    )
    return {
        "practice_id": practice.id,
        "description": practice.description or "",
        "attending_mentors": attending,
        "available_mentors": available,
    }


def practice_show_up_by_mentor(practice):
    """Map mentor_id -> show_up status for one practice."""
    return {
        row.mentor_id: row.show_up
        for row in practice.mentor_show_ups.all()
    }


def practice_attendance_mentor_rows(practice):
    """Assigned mentors with optional show-up status."""
    practice.sync_mentor_assignments_from_replies()
    show_up_by_mentor = practice_show_up_by_mentor(practice)
    rows = []
    seen = set()
    for mentor, pace, reply, assignment in practice.attending_mentor_roster_entries():
        assignment_payload = (
            practice_mentor_reply_payload(reply)
            if reply is not None
            else practice_mentor_assignment_payload(assignment)
        )
        rows.append(
            {
                **assignment_payload,
                "show_up": show_up_by_mentor.get(mentor.id),
                "swapped_out": False,
            }
        )
        seen.add(mentor.id)

    for show_up_row in practice.mentor_show_ups.select_related("mentor"):
        if show_up_row.mentor_id in seen:
            continue
        mentor = show_up_row.mentor
        rows.append(
            {
                "id": None,
                "mentor_id": mentor.id,
                "first_name": mentor.first_name,
                "last_name": mentor.last_name,
                "mentor_type": mentor.type,
                "attendance": PracticeAttendanceReply.ATTENDING,
                "pace": normalize_pace(mentor.pace or ""),
                "responded_at": show_up_row.updated_at.isoformat(),
                "scheduled_email_id": None,
                "scheduled_send_at": None,
                "show_up": show_up_row.show_up,
                "swapped_out": True,
            }
        )
    return rows


def build_practice_attendance_payload(practice, *, now=None):
    """Full attendance payload for one practice."""
    from datetime import timedelta

    from django.utils import timezone

    if now is None:
        now = timezone.now()
    return {
        "practice_id": practice.id,
        "date": practice.date.isoformat(),
        "nyrr_race": practice.nyrr_race or "",
        "description": practice.description or "",
        "start_location": practice.start_location or "",
        "season_id": practice.season_id,
        "season_year": practice.season.year,
        "full_practice": practice.full_practice,
        "attendance_comments": practice.attendance_comments or "",
        "assigned_mentors": practice_attendance_mentor_rows(practice),
        "is_current_window": practice.date >= now - timedelta(hours=24),
    }


def build_archived_practice_attendance_row(practice):
    """Summary row for archived practice attendance list."""
    mentors = practice_attendance_mentor_rows(practice)
    attended = sum(1 for row in mentors if row["show_up"] == ShowUpStatus.ATTENDED)
    missed = sum(1 for row in mentors if row["show_up"] == ShowUpStatus.MISSED)
    found_replacement = sum(
        1 for row in mentors if row["show_up"] == ShowUpStatus.FOUND_REPLACEMENT
    )
    return {
        "practice_id": practice.id,
        "date": practice.date.isoformat(),
        "nyrr_race": practice.nyrr_race or "",
        "season_id": practice.season_id,
        "season_year": practice.season.year,
        "assigned_count": sum(1 for row in mentors if not row.get("swapped_out")),
        "attended_count": attended,
        "missed_count": missed,
        "found_replacement_count": found_replacement,
        "unset_count": len(mentors) - attended - missed - found_replacement,
        "assigned_mentors": mentors,
    }


class PracticeSerializer(serializers.ModelSerializer):
    nyrr_race = serializers.CharField(
        max_length=150, allow_blank=True, required=False
    )
    start_location = serializers.CharField(
        max_length=255, allow_blank=True, required=False
    )
    mentors = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Mentor.objects.all(), required=False
    )

    class Meta:
        model = Practice
        fields = [
            "id",
            "date",
            "nyrr_race",
            "description",
            "start_location",
            "mentors",
            "full_practice",
            "show_to_mentors",
            "season",
            "attendance_comments",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PracticeDetailSerializer(PracticeSerializer):
    mentor_replies = serializers.SerializerMethodField()
    available_mentor_replies = serializers.SerializerMethodField()

    class Meta(PracticeSerializer.Meta):
        fields = PracticeSerializer.Meta.fields + [
            "mentor_replies",
            "available_mentor_replies",
        ]

    def get_mentor_replies(self, obj):
        obj.sync_mentor_assignments_from_replies()
        return practice_attending_mentor_payloads(obj)

    def get_available_mentor_replies(self, obj):
        return practice_available_mentor_payloads(obj)


class RequestsSerializer(serializers.ModelSerializer):
    practices = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Practice.objects.all(), required=False
    )

    class Meta:
        model = Requests
        fields = [
            "id",
            "date",
            "practices",
            "season",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CoachPracticeAssignmentSerializer(serializers.ModelSerializer):
    pace = serializers.CharField(max_length=11, allow_blank=True, required=False)

    class Meta:
        model = CoachPracticeAssignment
        fields = ["id", "coach", "practice", "pace", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_pace(self, value):
        if not (value or "").strip():
            return ""
        normalized = normalize_pace(value)
        if normalized not in {choice.value for choice in PaceTypes}:
            raise serializers.ValidationError("Invalid pace choice.")
        return normalized


class MentorPracticeAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MentorPracticeAssignment
        fields = ["id", "mentor", "practice", "pace", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ScheduledEmailSerializer(serializers.ModelSerializer):
    practices = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Practice.objects.all(), required=False
    )
    recipient_mode = serializers.ChoiceField(
        choices=ScheduledEmailRecipientMode.choices,
        required=False,
    )
    recipient_season = serializers.PrimaryKeyRelatedField(
        queryset=Season.objects.all(), allow_null=True, required=False
    )
    specific_mentors = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Mentor.objects.all(), required=False
    )
    reply_stats = serializers.SerializerMethodField()
    pending_mentors = serializers.SerializerMethodField()

    class Meta:
        model = ScheduledEmail
        fields = [
            "id",
            "scheduled_send_at",
            "task_completed_at",
            "recipients_emailed_count",
            "body_text",
            "practices",
            "recipient_mode",
            "recipient_season",
            "specific_mentors",
            "reply_stats",
            "pending_mentors",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "recipients_emailed_count",
            "reply_stats",
            "pending_mentors",
        ]

    def _sent_email_stats(self, obj):
        """Fresh reply stats for a sent email (cached per serializer instance)."""
        cache = self.context.setdefault("_scheduled_email_stats_cache", {})
        if obj.pk in cache:
            return cache[obj.pk]
        email = ScheduledEmail.objects.get(pk=obj.pk)
        stats = email.reply_stats()
        cache[obj.pk] = stats
        return stats

    def get_reply_stats(self, obj):
        if obj.task_completed_at:
            return self._sent_email_stats(obj)
        return obj.reply_stats()

    def get_pending_mentors(self, obj):
        if not obj.task_completed_at:
            return []
        stats = self._sent_email_stats(obj)
        pending = stats.get("pending_mentors")
        if isinstance(pending, list):
            return pending
        pending_ids = stats.get("pending_mentor_ids") or []
        if not pending_ids:
            return []
        mentors = Mentor.objects.filter(pk__in=pending_ids).order_by(
            "last_name", "first_name", "id"
        )
        return ScheduledEmail.serialize_pending_mentor_rows(mentors)

    def validate(self, attrs):
        instance = self.instance
        updating_recipients = (
            instance is None
            or "recipient_mode" in attrs
            or "recipient_season" in attrs
            or "specific_mentors" in attrs
        )
        if not updating_recipients:
            return attrs

        mode = attrs.get(
            "recipient_mode",
            getattr(
                instance,
                "recipient_mode",
                ScheduledEmailRecipientMode.ALL_IN_SEASON,
            )
            if instance
            else ScheduledEmailRecipientMode.ALL_IN_SEASON,
        )

        _unset = object()
        season = attrs.get("recipient_season", _unset)
        if season is _unset and instance is not None:
            season = instance.recipient_season

        mentors = attrs.get("specific_mentors", _unset)
        if mentors is _unset:
            mentors_list = (
                list(instance.specific_mentors.all()) if instance else []
            )
        else:
            mentors_list = list(mentors)

        if mode in (
            ScheduledEmailRecipientMode.ALL_IN_SEASON,
            ScheduledEmailRecipientMode.ALL_AT_PRACTICE_IN_SEASON,
            ScheduledEmailRecipientMode.ALL_REMOTE_IN_SEASON,
        ):
            if season is None:
                raise serializers.ValidationError(
                    {
                        "recipient_season": (
                            "Select a season when sending to mentors in that season."
                        )
                    }
                )
            attrs["recipient_season"] = season
            attrs["specific_mentors"] = []
        else:
            if not mentors_list:
                raise serializers.ValidationError(
                    {
                        "specific_mentors": (
                            "Select at least one mentor when using specific mentors."
                        )
                    }
                )
            attrs["specific_mentors"] = mentors_list
            attrs["recipient_season"] = None

        attrs["recipient_mode"] = mode
        return attrs


class PracticeReminderSendRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = PracticeReminderSendRecord
        fields = [
            "id",
            "recipient_email",
            "recipient_first_name",
            "recipient_last_name",
            "recipient_kind",
            "rendered_subject",
            "rendered_body",
            "sent_at",
            "created_at",
        ]
        read_only_fields = fields


class PracticeReminderEmailSerializer(serializers.ModelSerializer):
    send_records = PracticeReminderSendRecordSerializer(many=True, read_only=True)
    recipient_count = serializers.SerializerMethodField()
    pending_recipients = serializers.SerializerMethodField()
    scheduled_send_at = serializers.DateTimeField(required=False, allow_null=True)

    class Meta:
        model = PracticeReminderEmail
        fields = [
            "id",
            "season",
            "kind",
            "anchor_practice",
            "practice_one",
            "practice_two",
            "scheduled_send_at",
            "subject",
            "body_text",
            "task_completed_at",
            "recipients_emailed_count",
            "recipient_count",
            "pending_recipients",
            "send_records",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "season",
            "kind",
            "anchor_practice",
            "practice_one",
            "practice_two",
            "task_completed_at",
            "recipients_emailed_count",
            "recipient_count",
            "pending_recipients",
            "send_records",
            "created_at",
            "updated_at",
        ]

    def _pending_recipients_data(self, obj):
        cache = getattr(self, "_pending_recipients_cache", None)
        if cache is None:
            cache = {}
            self._pending_recipients_cache = cache
        if obj.pk not in cache:
            if obj.task_completed_at:
                cache[obj.pk] = []
            else:
                from .practice_reminder import pending_recipients_for_reminder

                cache[obj.pk] = pending_recipients_for_reminder(obj)
        return cache[obj.pk]

    def get_recipient_count(self, obj):
        if obj.task_completed_at:
            return obj.recipients_emailed_count or 0
        return len(self._pending_recipients_data(obj))

    def get_pending_recipients(self, obj):
        return self._pending_recipients_data(obj)

    def validate(self, attrs):
        instance = self.instance
        if instance and instance.task_completed_at:
            raise serializers.ValidationError(
                "Sent practice reminders cannot be edited."
            )
        return attrs
