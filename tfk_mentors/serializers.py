from rest_framework import serializers

from .models import (
    Coach,
    CoachPracticeAssignment,
    Mentor,
    MentorPracticeAssignment,
    MentorTypes,
    PaceTypes,
    Practice,
    Requests,
    ScheduledEmail,
    ScheduledEmailRecipientMode,
    Season,
    TfkStaff,
    normalize_pace,
)


class SeasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Season
        fields = ["id", "year", "is_current", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

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
        "scheduled_send_at": scheduled.scheduled_send_at.isoformat(),
    }


class PracticeSerializer(serializers.ModelSerializer):
    nyrr_race = serializers.CharField(
        max_length=150, allow_blank=True, required=False
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
            "mentors",
            "full_practice",
            "season",
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
        return [
            practice_mentor_reply_payload(r)
            for r in obj.latest_attending_mentor_replies()
        ]

    def get_available_mentor_replies(self, obj):
        return [
            practice_mentor_reply_payload(r)
            for r in obj.latest_available_mentor_replies()
        ]


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

        if mode == ScheduledEmailRecipientMode.ALL_IN_SEASON:
            if season is None:
                raise serializers.ValidationError(
                    {
                        "recipient_season": (
                            "Select a season when sending to all mentors in that season."
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
