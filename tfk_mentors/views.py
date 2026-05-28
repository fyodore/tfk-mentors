import csv
import io

from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
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
    Practice,
    PracticeAttendanceReply,
    Requests,
    ScheduledEmail,
    ScheduledEmailMentorPracticeReply,
    ScheduledEmailMentorToken,
    Season,
)
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


class RequestsViewSet(viewsets.ModelViewSet):
    """Full CRUD for Requests at /api/requests/."""

    queryset = (
        Requests.objects.all()
        .select_related("season")
        .prefetch_related("practices")
        .order_by("-date", "-id")
    )
    serializer_class = RequestsSerializer


def validate_practice_attendance(practice, mentor, attendance):
    """Raise ValueError if attendance is not allowed for this mentor/practice."""
    if mentor.type != MentorTypes.PRACTICE:
        raise ValueError("Only At Practice mentors may submit availability.")
    valid_vals = {c.value for c in PracticeAttendanceReply}
    if attendance not in valid_vals:
        raise ValueError("Invalid attendance choice.")
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


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MentorScheduledEmailReplyView(APIView):
    """Public mentor reply page backed by opaque UUID token."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, token):
        try:
            mt = ScheduledEmailMentorToken.objects.select_related(
                "scheduled_email", "mentor"
            ).get(token=token)
        except ScheduledEmailMentorToken.DoesNotExist:
            return Response(
                {"detail": "Invalid link."},
                status=status.HTTP_404_NOT_FOUND,
            )
        mentor = mt.mentor
        scheduled = mt.scheduled_email
        practices = scheduled.practices.select_related("season").order_by("date")
        reply_map = {r.practice_id: r.attendance for r in mt.practice_replies.all()}
        practice_payload = []
        for p in practices:
            practice_payload.append(
                {
                    "id": p.id,
                    "date": p.date.isoformat(),
                    "nyrr_race": p.nyrr_race or "",
                    "full_practice": p.full_practice,
                    "season_id": p.season_id,
                    "attendance": reply_map.get(p.id),
                }
            )
        return Response(
            {
                "mentor": {
                    "first_name": mentor.first_name,
                    "last_name": mentor.last_name,
                    "split_practice": mentor.split_practice,
                    "type": mentor.type,
                },
                "scheduled_send_at": scheduled.scheduled_send_at.isoformat(),
                "practices": practice_payload,
                "can_submit": mentor.type == MentorTypes.PRACTICE,
            }
        )

    def put(self, request, token):
        try:
            mt = ScheduledEmailMentorToken.objects.select_related(
                "scheduled_email", "mentor"
            ).get(token=token)
        except ScheduledEmailMentorToken.DoesNotExist:
            return Response(
                {"detail": "Invalid link."},
                status=status.HTTP_404_NOT_FOUND,
            )
        mentor = mt.mentor
        if mentor.type != MentorTypes.PRACTICE:
            return Response(
                {"detail": "Only At Practice mentors may submit availability."},
                status=status.HTTP_403_FORBIDDEN,
            )
        replies_in = request.data.get("replies")
        if not isinstance(replies_in, list):
            return Response(
                {"detail": "Expected 'replies' list."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        practice_ids = set(
            mt.scheduled_email.practices.values_list("pk", flat=True)
        )
        practices_by_id = {
            p.id: p for p in mt.scheduled_email.practices.all()
        }
        incoming = {}
        for item in replies_in:
            if not isinstance(item, dict):
                return Response(
                    {"detail": "Each reply must be an object."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            pid = item.get("practice")
            att = item.get("attendance")
            try:
                pid = int(pid)
            except (TypeError, ValueError):
                return Response(
                    {"detail": f"Invalid practice id: {pid!r}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if pid in incoming:
                return Response(
                    {"detail": f"Duplicate practice {pid}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if pid not in practice_ids:
                return Response(
                    {"detail": f"Practice {pid} is not part of this email."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            incoming[pid] = att
        if set(incoming.keys()) != practice_ids:
            return Response(
                {
                    "detail": "Submit exactly one reply per practice in this email.",
                    "missing": list(practice_ids - set(incoming.keys())),
                    "extra": list(set(incoming.keys()) - practice_ids),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        rows = []
        for pid, att in incoming.items():
            practice = practices_by_id[pid]
            try:
                validate_practice_attendance(practice, mentor, att)
            except ValueError as e:
                return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            rows.append(
                ScheduledEmailMentorPracticeReply(
                    mentor_token=mt,
                    practice_id=pid,
                    attendance=att,
                )
            )
        with transaction.atomic():
            mt.practice_replies.all().delete()
            ScheduledEmailMentorPracticeReply.objects.bulk_create(rows)
        return Response({"detail": "Saved.", "saved": len(rows)})


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
