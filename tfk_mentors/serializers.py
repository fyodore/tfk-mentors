from rest_framework import serializers

from .models import (
    Coach,
    CoachPracticeAssignment,
    Mentor,
    MentorPracticeAssignment,
    Practice,
    Requests,
    ScheduledEmail,
    ScheduledEmailRecipientMode,
    Season,
)


class SeasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Season
        fields = ["id", "year", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


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
        "pace": reply.pace or mentor.pace or "",
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
            "mentors",
            "full_practice",
            "season",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PracticeDetailSerializer(PracticeSerializer):
    mentor_replies = serializers.SerializerMethodField()

    class Meta(PracticeSerializer.Meta):
        fields = PracticeSerializer.Meta.fields + ["mentor_replies"]

    def get_mentor_replies(self, obj):
        obj.sync_mentor_assignments_from_replies()
        return [
            practice_mentor_reply_payload(r)
            for r in obj.latest_attending_mentor_replies()
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
    class Meta:
        model = CoachPracticeAssignment
        fields = ["id", "coach", "practice", "pace", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


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

    class Meta:
        model = ScheduledEmail
        fields = [
            "id",
            "scheduled_send_at",
            "task_completed_at",
            "body_text",
            "practices",
            "recipient_mode",
            "recipient_season",
            "specific_mentors",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

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
