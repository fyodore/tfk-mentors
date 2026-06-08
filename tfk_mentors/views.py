import csv
import io
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Coach,
    CoachPracticeAssignment,
    Mentor,
    MentorPracticeAssignment,
    MentorTypes,
    PaceTypes,
    Practice,
    PracticeAttendanceReply,
    Requests,
    ScheduledEmail,
    ScheduledEmailMentorPracticeReply,
    ScheduledEmailMentorToken,
    Season,
)

MIN_AT_PRACTICE_ATTENDANCE = 3
ATTENDING_REPLY_VALUES = frozenset(
    {
        PracticeAttendanceReply.ATTENDING,
        PracticeAttendanceReply.FIRST_HALF,
        PracticeAttendanceReply.SECOND_HALF,
    }
)
PACE_VALUES = frozenset(c.value for c in PaceTypes)
from .serializers import (
    CoachSerializer,
    CoachPracticeAssignmentSerializer,
    MentorSerializer,
    MentorPracticeAssignmentSerializer,
    PracticeSerializer,
    RequestsSerializer,
    ScheduledEmailSerializer,
    SeasonSerializer,
)


class SeasonViewSet(viewsets.ModelViewSet):
    """Full CRUD for Season at /api/season/."""

    queryset = Season.objects.all().order_by("-year", "-id")
    serializer_class = SeasonSerializer


class CoachViewSet(viewsets.ModelViewSet):
    """Full CRUD for Coach at /api/coach/."""

    queryset = Coach.objects.all().prefetch_related("seasons").order_by(
        "last_name", "first_name", "id"
    )
    serializer_class = CoachSerializer

    @action(detail=False, methods=["post"], url_path="import-csv")
    def import_csv(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {"detail": "CSV file is required in form field 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            text = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return Response(
                {"detail": "CSV file must be UTF-8 encoded."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return Response(
                {"detail": "CSV header row is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        required = {"email"}
        missing = [f for f in required if f not in reader.fieldnames]
        if missing:
            return Response(
                {"detail": f"Missing required CSV column(s): {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = 0
        updated = 0
        skipped = 0
        errors = []
        created_by_season = {}

        for row_num, row in enumerate(reader, start=2):
            email = (row.get("email") or "").strip().lower()
            if not email:
                skipped += 1
                continue

            season_raw = (
                row.get("season_year")
                or row.get("season")
                or row.get("year")
                or ""
            ).strip()
            if not season_raw:
                errors.append(f"row {row_num}: season_year/season/year is required")
                continue
            try:
                season_year = int(season_raw)
            except ValueError:
                errors.append(f"row {row_num}: invalid season year '{season_raw}'")
                continue

            season = Season.objects.filter(year=season_year).first()
            if season is None:
                errors.append(f"row {row_num}: season {season_year} does not exist")
                continue

            defaults = {
                "first_name": (row.get("first_name") or "").strip(),
                "last_name": (row.get("last_name") or "").strip(),
                "cell": (row.get("cell") or "").strip(),
            }
            coach = Coach.objects.filter(email=email).first()
            if coach is None:
                coach = Coach(email=email, **defaults)
                if not coach.first_name or not coach.last_name:
                    errors.append(
                        f"row {row_num}: first_name and last_name required for new coach"
                    )
                    continue
                coach.save()
                created += 1
                created_by_season[season_year] = created_by_season.get(season_year, 0) + 1
            else:
                changed = False
                for field, value in defaults.items():
                    if value and getattr(coach, field) != value:
                        setattr(coach, field, value)
                        changed = True
                if changed:
                    coach.save(update_fields=["first_name", "last_name", "cell"])
                updated += 1

            coach.seasons.add(season)

        code = status.HTTP_207_MULTI_STATUS if errors else status.HTTP_200_OK
        return Response(
            {
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "created_by_season": created_by_season,
                "errors": errors,
            },
            status=code,
        )


class MentorViewSet(viewsets.ModelViewSet):
    """Full CRUD for Mentor at /api/mentor/."""

    queryset = Mentor.objects.all().prefetch_related("seasons").order_by(
        "last_name", "first_name", "id"
    )
    serializer_class = MentorSerializer

    @action(detail=False, methods=["post"], url_path="import-csv")
    def import_csv(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {"detail": "CSV file is required in form field 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            text = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return Response(
                {"detail": "CSV file must be UTF-8 encoded."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return Response(
                {"detail": "CSV header row is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        required = {"email"}
        missing = [f for f in required if f not in reader.fieldnames]
        if missing:
            return Response(
                {"detail": f"Missing required CSV column(s): {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        def parse_bool(v):
            return str(v).strip().lower() in {"1", "true", "yes", "y"}

        created = 0
        updated = 0
        skipped = 0
        errors = []
        created_by_season = {}

        for row_num, row in enumerate(reader, start=2):
            email = (row.get("email") or "").strip().lower()
            if not email:
                skipped += 1
                continue

            season_raw = (
                row.get("season_year")
                or row.get("season")
                or row.get("year")
                or ""
            ).strip()
            if not season_raw:
                errors.append(f"row {row_num}: season_year/season/year is required")
                continue
            try:
                season_year = int(season_raw)
            except ValueError:
                errors.append(f"row {row_num}: invalid season year '{season_raw}'")
                continue

            season = Season.objects.filter(year=season_year).first()
            if season is None:
                errors.append(f"row {row_num}: season {season_year} does not exist")
                continue

            defaults = {
                "first_name": (row.get("first_name") or "").strip(),
                "last_name": (row.get("last_name") or "").strip(),
                "cell_phone": (row.get("cell_phone") or row.get("cell") or "").strip(),
                "type": (row.get("type") or "").strip(),
                "pace": (row.get("pace") or "").strip(),
                "split_practice": parse_bool(row.get("split_practice") or ""),
            }

            mentor = Mentor.objects.filter(email=email).first()
            if mentor is None:
                mentor = Mentor(email=email, **defaults)
                required_new = ["first_name", "last_name", "cell_phone", "type", "pace"]
                missing_new = [f for f in required_new if not getattr(mentor, f)]
                if missing_new:
                    errors.append(
                        f"row {row_num}: missing required fields for new mentor: "
                        + ", ".join(missing_new)
                    )
                    continue
                mentor.save()
                created += 1
                created_by_season[season_year] = created_by_season.get(season_year, 0) + 1
            else:
                changed = False
                for field in ["first_name", "last_name", "cell_phone", "type", "pace"]:
                    value = defaults[field]
                    if value and getattr(mentor, field) != value:
                        setattr(mentor, field, value)
                        changed = True
                if "split_practice" in row and mentor.split_practice != defaults["split_practice"]:
                    mentor.split_practice = defaults["split_practice"]
                    changed = True
                if changed:
                    mentor.save()
                updated += 1

            mentor.seasons.add(season)

        code = status.HTTP_207_MULTI_STATUS if errors else status.HTTP_200_OK
        return Response(
            {
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "created_by_season": created_by_season,
                "errors": errors,
            },
            status=code,
        )


class PracticeViewSet(viewsets.ModelViewSet):
    """Full CRUD for Practice at /api/practice/."""

    queryset = (
        Practice.objects.all()
        .select_related("season")
        .prefetch_related("mentors")
        .order_by("-date", "-id")
    )
    serializer_class = PracticeSerializer

    @action(detail=True, methods=["get", "post", "delete"], url_path="mentor-replies")
    def mentor_replies(self, request, pk=None):
        """Mentors assigned to this practice via ScheduledEmailMentorPracticeReply."""
        practice = self.get_object()

        if request.method == "GET":
            practice.sync_mentor_assignments_from_replies()
            return Response(
                [
                    practice_mentor_reply_payload(r)
                    for r in practice.latest_attending_mentor_replies()
                ]
            )

        if request.method == "POST":
            mentor_id = request.data.get("mentor")
            pace = (request.data.get("pace") or "").strip()
            try:
                mentor_id = int(mentor_id)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "Invalid mentor id."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                mentor = Mentor.objects.get(pk=mentor_id)
            except Mentor.DoesNotExist:
                return Response(
                    {"detail": "Mentor not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if not mentor.seasons.filter(id=practice.season_id).exists():
                return Response(
                    {"detail": "Mentor must belong to the practice season."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not pace:
                pace = mentor.pace
            if pace not in PACE_VALUES:
                return Response(
                    {"detail": "Invalid pace choice."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                mentor_token = practice.get_or_create_mentor_reply_token(mentor)
            except ValidationError as e:
                return Response(
                    {"detail": e.messages[0] if e.messages else str(e)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            with transaction.atomic():
                reply, _ = ScheduledEmailMentorPracticeReply.objects.update_or_create(
                    mentor_token=mentor_token,
                    practice=practice,
                    defaults={
                        "mentor": mentor,
                        "attendance": PracticeAttendanceReply.ATTENDING,
                        "pace": pace,
                    },
                )
                practice.sync_mentor_assignments_from_replies()
            return Response(
                practice_mentor_reply_payload(reply),
                status=status.HTTP_201_CREATED,
            )

        mentor_id = request.data.get("mentor") or request.query_params.get("mentor")
        try:
            mentor_id = int(mentor_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "Invalid mentor id."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            ScheduledEmailMentorPracticeReply.objects.filter(
                practice=practice,
                mentor_id=mentor_id,
            ).update(
                attendance=PracticeAttendanceReply.NOT_ATTENDING,
                pace="",
            )
            practice.sync_mentor_assignments_from_replies()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RequestsViewSet(viewsets.ModelViewSet):
    """Full CRUD for Requests at /api/requests/."""

    queryset = (
        Requests.objects.all()
        .select_related("season")
        .prefetch_related("practices")
        .order_by("-date", "-id")
    )
    serializer_class = RequestsSerializer


def mentor_reply_payload(mentor):
    """Full mentor record for the public reply page."""
    return {
        "id": mentor.id,
        "first_name": mentor.first_name,
        "last_name": mentor.last_name,
        "email": mentor.email,
        "cell_phone": mentor.cell_phone,
        "type": mentor.type,
        "pace": mentor.pace,
        "split_practice": mentor.split_practice,
        "season_years": list(
            mentor.seasons.order_by("-year").values_list("year", flat=True)
        ),
    }


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


def season_year_for_scheduled_email(scheduled):
    return scheduled.resolve_season_year()


def count_attending_replies(replies_by_practice_id):
    return sum(
        1
        for att in replies_by_practice_id.values()
        if att in ATTENDING_REPLY_VALUES
    )


def validate_practice_attendance(practice, mentor, attendance):
    """Raise ValueError if attendance is not allowed for this mentor/practice."""
    valid_vals = {c.value for c in PracticeAttendanceReply}
    if attendance not in valid_vals:
        raise ValueError("Invalid attendance choice.")
    if mentor.type == MentorTypes.REMOTE:
        if attendance not in (
            PracticeAttendanceReply.ATTENDING,
            PracticeAttendanceReply.NOT_ATTENDING,
        ):
            raise ValueError("Remote mentors may only mark attending or not attending.")
        return
    if practice.full_practice:
        if attendance not in (
            PracticeAttendanceReply.ATTENDING,
            PracticeAttendanceReply.NOT_ATTENDING,
        ):
            raise ValueError("For a full practice, choose attending or not attending.")
        return
    if mentor.split_practice:
        if attendance not in (
            PracticeAttendanceReply.FIRST_HALF,
            PracticeAttendanceReply.SECOND_HALF,
            PracticeAttendanceReply.NOT_ATTENDING,
        ):
            raise ValueError(
                "For this split practice, choose first half, second half, or not attending."
            )
    elif attendance not in (
        PracticeAttendanceReply.ATTENDING,
        PracticeAttendanceReply.NOT_ATTENDING,
    ):
        raise ValueError("Choose attending or not attending.")


def validate_reply_pace(mentor, attendance, pace):
    """Raise ValueError if pace is missing or invalid for this reply."""
    if attendance not in ATTENDING_REPLY_VALUES:
        if pace:
            raise ValueError("Pace should only be set when attending a practice.")
        return
    if mentor.type == MentorTypes.REMOTE:
        if not pace:
            raise ValueError("Select a pace for each practice you plan to attend.")
        if pace not in PACE_VALUES:
            raise ValueError("Invalid pace choice.")
        return
    if pace and pace not in PACE_VALUES:
        raise ValueError("Invalid pace choice.")


@method_decorator(ensure_csrf_cookie, name="dispatch")
class SiteAuthView(APIView):
    """Site password login for admin SPA (session cookie)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {"authenticated": request.session.get("site_authenticated") is True}
        )

    def post(self, request):
        password = request.data.get("password", "")
        if password != settings.SITE_PASSWORD:
            return Response(
                {"detail": "Invalid password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        request.session["site_authenticated"] = True
        request.session.set_expiry(60 * 60 * 24 * 14)  # 14 days
        return Response({"detail": "Authenticated."})

    def delete(self, request):
        request.session.flush()
        return Response({"detail": "Logged out."})


@method_decorator(csrf_exempt, name="dispatch")
class MentorScheduledEmailReplyView(APIView):
    """Public mentor reply page backed by opaque UUID token (?token= or path)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def _resolve_token(self, request, token=None):
        if token is not None:
            return token
        raw = request.GET.get("token")
        if not raw:
            return None
        try:
            return uuid.UUID(str(raw).strip())
        except (TypeError, ValueError, AttributeError):
            return None

    def _get_token_row(self, request, token=None):
        resolved = self._resolve_token(request, token)
        if resolved is None:
            return None, Response(
                {"detail": "Missing or invalid token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            mt = ScheduledEmailMentorToken.objects.select_related(
                "scheduled_email__recipient_season", "mentor"
            ).prefetch_related("mentor__seasons").get(token=resolved)
        except ScheduledEmailMentorToken.DoesNotExist:
            return None, Response(
                {"detail": "Invalid link."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return mt, None

    def get(self, request, token=None):
        mt, err = self._get_token_row(request, token)
        if err is not None:
            return err
        mentor = mt.mentor
        scheduled = mt.scheduled_email
        practices = scheduled.practices.select_related("season").order_by("date")
        reply_map = {
            r.practice_id: r for r in mt.practice_replies.all()
        }
        practice_payload = []
        for p in practices:
            saved = reply_map.get(p.id)
            practice_payload.append(
                {
                    "id": p.id,
                    "date": p.date.isoformat(),
                    "nyrr_race": p.nyrr_race or "",
                    "full_practice": p.full_practice,
                    "season_id": p.season_id,
                    "attendance": saved.attendance if saved else None,
                    "pace": (saved.pace or "") if saved else "",
                }
            )
        season_year = season_year_for_scheduled_email(scheduled)
        assigned_pace = scheduled.resolve_pace_for_mentor(mentor)
        return Response(
            {
                "mentor": mentor_reply_payload(mentor),
                "season_year": season_year,
                "assigned_pace": assigned_pace or "",
                "scheduled_send_at": scheduled.scheduled_send_at.isoformat(),
                "practices": practice_payload,
                "pace_choices": [c.value for c in PaceTypes],
                "email_received_confirmed": mt.email_received_confirmed,
                "min_at_practice_attendance": MIN_AT_PRACTICE_ATTENDANCE,
            }
        )

    def put(self, request, token=None):
        mt, err = self._get_token_row(request, token)
        if err is not None:
            return err
        mentor = mt.mentor
        replies_in = request.data.get("replies")
        if not isinstance(replies_in, list):
            return Response(
                {"detail": "Expected 'replies' list."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        email_confirmed = request.data.get("email_received_confirmed")
        if mentor.type == MentorTypes.REMOTE:
            if email_confirmed is not True:
                return Response(
                    {
                        "detail": "Please confirm that you received the email.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        practice_ids = set(
            mt.scheduled_email.practices.values_list("pk", flat=True)
        )
        practices_by_id = {
            p.id: p for p in mt.scheduled_email.practices.all()
        }
        incoming_attendance = {}
        incoming_pace = {}
        for item in replies_in:
            if not isinstance(item, dict):
                return Response(
                    {"detail": "Each reply must be an object."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            pid = item.get("practice")
            att = item.get("attendance")
            pace = item.get("pace") or ""
            try:
                pid = int(pid)
            except (TypeError, ValueError):
                return Response(
                    {"detail": f"Invalid practice id: {pid!r}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if pid in incoming_attendance:
                return Response(
                    {"detail": f"Duplicate practice {pid}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if pid not in practice_ids:
                return Response(
                    {"detail": f"Practice {pid} is not part of this email."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            incoming_attendance[pid] = att
            incoming_pace[pid] = pace
        if set(incoming_attendance.keys()) != practice_ids:
            return Response(
                {
                    "detail": "Submit exactly one reply per practice in this email.",
                    "missing": list(practice_ids - set(incoming_attendance.keys())),
                    "extra": list(set(incoming_attendance.keys()) - practice_ids),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if mentor.type == MentorTypes.PRACTICE:
            attending_count = count_attending_replies(incoming_attendance)
            if attending_count < MIN_AT_PRACTICE_ATTENDANCE:
                return Response(
                    {
                        "detail": (
                            f"Select at least {MIN_AT_PRACTICE_ATTENDANCE} practices "
                            "you can attend."
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        rows = []
        for pid, att in incoming_attendance.items():
            practice = practices_by_id[pid]
            pace = incoming_pace.get(pid) or ""
            try:
                validate_practice_attendance(practice, mentor, att)
                validate_reply_pace(mentor, att, pace)
            except ValueError as e:
                return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            rows.append(
                ScheduledEmailMentorPracticeReply(
                    mentor_token=mt,
                    mentor=mentor,
                    practice_id=pid,
                    attendance=att,
                    pace=pace if att in ATTENDING_REPLY_VALUES else "",
                )
            )
        with transaction.atomic():
            mt.email_received_confirmed = (
                email_confirmed is True
                if mentor.type == MentorTypes.REMOTE
                else mt.email_received_confirmed
            )
            mt.save(update_fields=["email_received_confirmed", "updated_at"])
            mt.practice_replies.all().delete()
            ScheduledEmailMentorPracticeReply.objects.bulk_create(rows)
            for pid in practice_ids:
                Practice.objects.get(pk=pid).sync_mentor_assignments_from_replies()
        saved_replies = (
            ScheduledEmailMentorPracticeReply.objects.filter(mentor_token=mt)
            .select_related("practice")
            .order_by("practice__date")
        )
        return Response(
            {
                "detail": "Saved.",
                "saved": len(rows),
                "mentor_id": mentor.id,
                "replies": [
                    {
                        "practice": r.practice_id,
                        "attendance": r.attendance,
                        "pace": r.pace or "",
                    }
                    for r in saved_replies
                ],
            }
        )


class ScheduledEmailViewSet(viewsets.ModelViewSet):
    """CRUD for scheduled mentor emails at /api/scheduled-email/."""

    queryset = (
        ScheduledEmail.objects.all()
        .select_related("recipient_season")
        .prefetch_related("practices", "specific_mentors")
        .order_by("-scheduled_send_at", "-id")
    )
    serializer_class = ScheduledEmailSerializer

    def perform_create(self, serializer):
        instance = serializer.save()
        instance.sync_mentor_tokens()

    def perform_update(self, serializer):
        instance = serializer.save()
        instance.sync_mentor_tokens()


class CoachPracticeAssignmentViewSet(viewsets.ModelViewSet):
    """CRUD for CoachPracticeAssignment at /api/coach-practice-assignment/."""

    queryset = (
        CoachPracticeAssignment.objects.all()
        .select_related("coach", "practice")
        .order_by("-id")
    )
    serializer_class = CoachPracticeAssignmentSerializer


class MentorPracticeAssignmentViewSet(viewsets.ModelViewSet):
    """CRUD for MentorPracticeAssignment at /api/mentor-practice-assignment/."""

    queryset = (
        MentorPracticeAssignment.objects.all()
        .select_related("mentor", "practice")
        .order_by("-id")
    )
    serializer_class = MentorPracticeAssignmentSerializer
