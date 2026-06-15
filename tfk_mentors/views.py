import calendar
import csv
import io
import uuid
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch
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
    PACE_SORT,
    Practice,
    PracticeAttendanceReply,
    Requests,
    ScheduledEmail,
    ScheduledEmailMentorPracticeReply,
    ScheduledEmailMentorToken,
    Season,
    TfkStaff,
    normalize_pace,
)

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
    PracticeDetailSerializer,
    PracticeSerializer,
    RequestsSerializer,
    ScheduledEmailSerializer,
    SeasonSerializer,
    TfkStaffSerializer,
    practice_mentor_reply_payload,
)
from .email_sending import send_reply_reminders as send_reply_reminders_for_email
from .email_sending import send_scheduled_email as send_scheduled_email_now


def normalize_csv_header_key(key):
    if key is None:
        return ""
    return key.strip().lower().replace(" ", "_")


def normalize_csv_row(row):
    normalized = {}
    for key, value in row.items():
        norm_key = normalize_csv_header_key(key)
        if norm_key:
            normalized[norm_key] = value
    return normalized


def clean_csv_cell(value):
    if value is None:
        return ""
    text = str(value).replace("\ufeff", "").replace("\u200b", "").replace("\xa0", " ")
    return text.strip().strip('"').strip("'").lstrip("'")


def csv_row_value(row, *keys):
    for key in keys:
        norm_key = normalize_csv_header_key(key)
        value = row.get(norm_key)
        cleaned = clean_csv_cell(value)
        if cleaned:
            return cleaned
    return ""


def normalize_csv_mentor_type(raw):
    """Map CSV type values to canonical MentorTypes labels."""
    value = clean_csv_cell(raw)
    if not value:
        return ""
    folded = value.casefold()
    for choice in MentorTypes:
        if folded == choice.value.casefold():
            return choice.value
    if folded in {"remote", "r"} or folded.startswith("remote"):
        return MentorTypes.REMOTE
    if folded in {"at practice", "practice", "ap", "in person", "in-person"}:
        return MentorTypes.PRACTICE
    if "practice" in folded and "remote" not in folded:
        return MentorTypes.PRACTICE
    return value


def csv_mentor_is_remote(mentor_type):
    if not mentor_type:
        return False
    if mentor_type == MentorTypes.REMOTE:
        return True
    return normalize_csv_mentor_type(str(mentor_type)) == MentorTypes.REMOTE


def csv_mentor_requires_cell_phone(mentor_type):
    return not csv_mentor_is_remote(mentor_type)


def open_csv_dict_reader(text):
    """Parse CSV exports from Excel/Sheets (comma, semicolon, or tab)."""
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return csv.DictReader(io.StringIO(text), dialect=dialect)


class SeasonViewSet(viewsets.ModelViewSet):
    """Full CRUD for Season at /api/season/."""

    queryset = Season.objects.all().order_by("-year", "-id")
    serializer_class = SeasonSerializer

    def _clear_other_current_seasons(self, keep_id=None):
        queryset = Season.objects.filter(is_current=True)
        if keep_id is not None:
            queryset = queryset.exclude(pk=keep_id)
        queryset.update(is_current=False)

    def create(self, request, *args, **kwargs):
        if request.data.get("is_current") is True:
            self._clear_other_current_seasons()
        return super().create(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if request.data.get("is_current") is True:
            self._clear_other_current_seasons(keep_id=kwargs.get("pk"))
        return super().partial_update(request, *args, **kwargs)


class TfkStaffViewSet(viewsets.ModelViewSet):
    """Full CRUD for TFK staff at /api/tfk-staff/."""

    queryset = TfkStaff.objects.all().order_by("last_name", "first_name", "id")
    serializer_class = TfkStaffSerializer


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

        reader = open_csv_dict_reader(text)
        if not reader.fieldnames:
            return Response(
                {"detail": "CSV header row is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized_fieldnames = {
            normalize_csv_header_key(name) for name in reader.fieldnames
        }
        if "email" not in normalized_fieldnames:
            return Response(
                {"detail": "Missing required CSV column(s): email"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        def parse_bool(v):
            return str(v).strip().lower() in {"1", "true", "yes", "y"}

        created = 0
        updated = 0
        skipped = 0
        errors = []
        created_by_season = {}

        for row_num, raw_row in enumerate(reader, start=2):
            row = normalize_csv_row(raw_row)
            email = csv_row_value(row, "email").lower()
            if not email:
                skipped += 1
                continue

            season_raw = csv_row_value(row, "season_year", "season", "year")
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

            raw_pace = csv_row_value(row, "pace")
            pace = normalize_pace(raw_pace) if raw_pace else ""
            if raw_pace and pace not in PACE_VALUES:
                errors.append(
                    f"row {row_num}: invalid pace '{raw_pace}'"
                    + (f" (normalized to '{pace}')" if pace != raw_pace else "")
                )
                continue

            raw_type = csv_row_value(row, "type", "mentor_type")
            mentor_type = normalize_csv_mentor_type(raw_type)
            if mentor_type and mentor_type not in {
                c.value for c in MentorTypes
            }:
                errors.append(
                    f"row {row_num}: invalid type '{raw_type or row.get('type')}'"
                )
                continue

            defaults = {
                "first_name": csv_row_value(row, "first_name", "firstname"),
                "last_name": csv_row_value(row, "last_name", "lastname"),
                "cell_phone": csv_row_value(
                    row, "cell_phone", "cell", "phone", "mobile"
                ),
                "type": mentor_type,
                "pace": pace,
                "split_practice": parse_bool(
                    csv_row_value(row, "split_practice") or "false"
                ),
            }

            mentor = Mentor.objects.filter(email=email).first()
            if mentor is None:
                mentor = Mentor(email=email, **defaults)
                required_new = ["first_name", "last_name", "type"]
                if csv_mentor_requires_cell_phone(defaults["type"]):
                    required_new.append("cell_phone")
                missing_new = [f for f in required_new if not getattr(mentor, f)]
                if missing_new:
                    detail = ", ".join(missing_new)
                    if "cell_phone" in missing_new and defaults["type"]:
                        detail += (
                            f" (type was read as '{defaults['type']}'; "
                            "only At Practice mentors require cell_phone)"
                        )
                    elif "cell_phone" in missing_new:
                        detail += (
                            " (type column is missing or empty; "
                            "set type to Remote to skip cell_phone)"
                        )
                    errors.append(
                        f"row {row_num}: missing required fields for new mentor: "
                        + detail
                    )
                    continue
                if csv_mentor_requires_cell_phone(defaults["type"]) and not pace:
                    errors.append(
                        f"row {row_num}: pace is required for At Practice mentors"
                    )
                    continue
                mentor.save()
                created += 1
                created_by_season[season_year] = created_by_season.get(season_year, 0) + 1
            else:
                changed = False
                for field in ["first_name", "last_name", "cell_phone", "type", "pace"]:
                    value = defaults[field]
                    if field == "pace":
                        if defaults["type"] == MentorTypes.REMOTE and not value:
                            if mentor.pace:
                                mentor.pace = ""
                                changed = True
                            continue
                        if csv_mentor_requires_cell_phone(defaults["type"]) and not value:
                            continue
                    if field == "cell_phone" and defaults["type"] == MentorTypes.REMOTE:
                        if getattr(mentor, field) != value:
                            setattr(mentor, field, value)
                            changed = True
                        continue
                    if value and getattr(mentor, field) != value:
                        setattr(mentor, field, value)
                        changed = True
                if (
                    csv_mentor_requires_cell_phone(defaults["type"])
                    and not mentor.pace
                    and not defaults["pace"]
                ):
                    errors.append(
                        f"row {row_num}: pace is required for At Practice mentors"
                    )
                    continue
                if (
                    csv_mentor_requires_cell_phone(defaults["type"])
                    and not (mentor.cell_phone or "").strip()
                    and not defaults["cell_phone"]
                ):
                    errors.append(
                        f"row {row_num}: cell phone is required for At Practice mentors"
                    )
                    continue
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
                "import_rules_version": 2,
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

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PracticeDetailSerializer
        return PracticeSerializer

    @action(
        detail=True,
        methods=["get", "post", "patch", "delete"],
        url_path="mentor-replies",
    )
    def mentor_replies(self, request, pk=None):
        """Mentors assigned to this practice via ScheduledEmailMentorPracticeReply."""
        practice = self.get_object()

        if request.method == "GET":
            practice.sync_mentor_assignments_from_replies()
            return Response(
                {
                    "mentors": [
                        practice_mentor_reply_payload(r)
                        for r in practice.latest_attending_mentor_replies()
                    ],
                    "available_mentors": [
                        practice_mentor_reply_payload(r)
                        for r in practice.latest_available_mentor_replies()
                    ],
                }
            )

        if request.method == "PATCH":
            mentor_id = request.data.get("mentor")
            attendance = (request.data.get("attendance") or "").strip()
            try:
                mentor_id = int(mentor_id)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "Invalid mentor id."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if attendance != PracticeAttendanceReply.AVAILABLE:
                return Response(
                    {"detail": "Only 'available' attendance is supported."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            reply = (
                ScheduledEmailMentorPracticeReply.objects.filter(
                    practice=practice,
                    mentor_id=mentor_id,
                    attendance__in=ATTENDING_REPLY_VALUES,
                )
                .select_related("mentor", "mentor_token__scheduled_email")
                .order_by("-updated_at")
                .first()
            )
            if reply is None:
                return Response(
                    {"detail": "Mentor is not assigned to this practice."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            with transaction.atomic():
                reply.attendance = PracticeAttendanceReply.AVAILABLE
                reply.save(update_fields=["attendance", "updated_at"])
                practice.sync_mentor_assignments_from_replies()
            return Response(practice_mentor_reply_payload(reply))

        if request.method == "POST":
            mentor_id = request.data.get("mentor")
            pace = normalize_pace((request.data.get("pace") or "").strip())
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
                pace = normalize_pace(mentor.pace or "")
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


def season_year_for_scheduled_email(scheduled):
    return scheduled.resolve_season_year()


def display_timezone():
    return ZoneInfo(settings.TIME_ZONE)


def practice_local_date(practice):
    return practice.date.astimezone(display_timezone())


def email_shows_partial_month(practices):
    """True when listed practices do not cover a full calendar month."""
    by_month = {}
    for practice in practices:
        local = practice_local_date(practice)
        key = (local.year, local.month)
        last_day = calendar.monthrange(local.year, local.month)[1]
        if key not in by_month:
            by_month[key] = {"min": local.day, "max": local.day, "last": last_day}
        else:
            stats = by_month[key]
            stats["min"] = min(stats["min"], local.day)
            stats["max"] = max(stats["max"], local.day)
    for stats in by_month.values():
        if stats["min"] > 1 or stats["max"] < stats["last"]:
            return True
    return False


def validate_practice_attendance(practice, mentor, attendance):
    """Raise ValueError if attendance is not allowed for this mentor/practice."""
    valid_vals = {c.value for c in PracticeAttendanceReply}
    if attendance not in valid_vals:
        raise ValueError("Invalid attendance choice.")
    if attendance == PracticeAttendanceReply.AVAILABLE:
        return
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


PACE_REQUIRED_REPLY_VALUES = ATTENDING_REPLY_VALUES | {
    PracticeAttendanceReply.AVAILABLE,
}


def validate_reply_pace(mentor, attendance, pace):
    """Raise ValueError if pace is missing or invalid for this reply."""
    pace = normalize_pace(pace) if pace else ""
    if attendance not in PACE_REQUIRED_REPLY_VALUES:
        if pace:
            raise ValueError("Pace should only be set when attending a practice.")
        return
    if mentor.type == MentorTypes.REMOTE:
        if not pace:
            raise ValueError(
                "Select your pace group for the practices you plan to attend."
            )
        if pace not in PACE_VALUES:
            raise ValueError("Invalid pace choice.")
        return
    if pace and pace not in PACE_VALUES:
        raise ValueError("Invalid pace choice.")


def _latest_replies_from_prefetch(practice, attendance_values):
    """Latest reply per mentor for attendance values, using prefetched replies when set."""
    latest_by_mentor = {}
    for reply in practice.mentor_email_replies.all():
        if reply.attendance not in attendance_values:
            continue
        existing = latest_by_mentor.get(reply.mentor_id)
        if existing is None or reply.updated_at > existing.updated_at:
            latest_by_mentor[reply.mentor_id] = reply
    return sorted(
        latest_by_mentor.values(),
        key=lambda reply: (reply.mentor.last_name, reply.mentor.first_name),
    )


def mentors_from_practice_replies(practice):
    """Latest attending mentor reply per mentor, using prefetched replies when available."""
    return _latest_replies_from_prefetch(practice, ATTENDING_REPLY_VALUES)


def mentors_available_from_practice_replies(practice):
    """Latest available mentor reply per mentor, using prefetched replies when available."""
    return _latest_replies_from_prefetch(
        practice, {PracticeAttendanceReply.AVAILABLE}
    )


def mentor_pace_counts_from_rows(mentor_rows, *, include_zero=False):
    """Count attending mentors per pace group for report display."""
    counts = {choice.value: 0 for choice in PaceTypes}
    for row in mentor_rows:
        pace = normalize_pace(row.get("pace") or "")
        if pace in counts:
            counts[pace] += 1
    rows = [
        {"pace": choice.value, "count": counts[choice.value]}
        for choice in PaceTypes
    ]
    if include_zero:
        return rows
    return [row for row in rows if row["count"] > 0]


def email_response_pace_counts(tokens, replied_pairs, practice_id):
    """Per-pace emailed / responded / pending counts for one practice email."""
    emailed = {choice.value: 0 for choice in PaceTypes}
    responded = {choice.value: 0 for choice in PaceTypes}
    pending = {choice.value: 0 for choice in PaceTypes}
    for token in tokens:
        pace = token.mentor.pace or ""
        if pace not in emailed:
            continue
        emailed[pace] += 1
        if (token.id, practice_id) in replied_pairs:
            responded[pace] += 1
        else:
            pending[pace] += 1
    return [
        {
            "pace": choice.value,
            "emailed": emailed[choice.value],
            "responded": responded[choice.value],
            "pending": pending[choice.value],
        }
        for choice in PaceTypes
    ]


def build_practice_roster_report(practices):
    """Serialize practices with attending coaches and mentors for admin reports."""
    report = []
    for practice in practices:
        coaches = []
        for assignment in practice.coachpracticeassignment_set.all():
            coach = assignment.coach
            coaches.append(
                {
                    "role": "Coach",
                    "first_name": coach.first_name,
                    "last_name": coach.last_name,
                    "email": coach.email,
                    "pace": assignment.pace,
                }
            )

        mentors = []
        for reply in mentors_from_practice_replies(practice):
            mentor = reply.mentor
            mentors.append(
                {
                    "mentor_id": mentor.id,
                    "role": "Mentor",
                    "first_name": mentor.first_name,
                    "last_name": mentor.last_name,
                    "email": mentor.email,
                    "pace": normalize_pace(reply.pace or mentor.pace or ""),
                    "mentor_type": mentor.type,
                    "attendance": reply.attendance,
                    "available": False,
                }
            )

        available_mentors = []
        for reply in mentors_available_from_practice_replies(practice):
            mentor = reply.mentor
            available_mentors.append(
                {
                    "mentor_id": mentor.id,
                    "role": "Mentor",
                    "first_name": mentor.first_name,
                    "last_name": mentor.last_name,
                    "email": mentor.email,
                    "pace": normalize_pace(reply.pace or mentor.pace or ""),
                    "mentor_type": mentor.type,
                    "attendance": reply.attendance,
                    "available": True,
                }
            )

        report.append(
            {
                "id": practice.id,
                "date": practice.date.isoformat(),
                "nyrr_race": practice.nyrr_race or "",
                "season": practice.season_id,
                "season_year": practice.season.year,
                "full_practice": practice.full_practice,
                "coaches": coaches,
                "mentors": mentors,
                "available_mentors": available_mentors,
                "mentor_pace_counts": mentor_pace_counts_from_rows(
                    mentors, include_zero=True
                ),
            }
        )
    return report


class PracticeRosterReportView(APIView):
    """Practice roster report: coaches and attending mentors per practice."""

    def get(self, request):
        season_raw = (request.query_params.get("season") or "").strip()
        if season_raw:
            try:
                int(season_raw)
            except ValueError:
                return Response(
                    {"detail": "Invalid season id."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        queryset = (
            _practice_report_queryset(season_raw)
            .prefetch_related(
                Prefetch(
                    "coachpracticeassignment_set",
                    queryset=CoachPracticeAssignment.objects.select_related("coach"),
                ),
                Prefetch(
                    "mentor_email_replies",
                    queryset=ScheduledEmailMentorPracticeReply.objects.filter(
                        attendance__in=ATTENDING_REPLY_VALUES
                        | {PracticeAttendanceReply.AVAILABLE}
                    )
                    .select_related("mentor", "mentor_token__scheduled_email")
                    .order_by("-updated_at"),
                ),
            )
        )
        return Response(build_practice_roster_report(list(queryset)))


def _practice_report_queryset(season_raw):
    queryset = Practice.objects.all().select_related("season").order_by("date", "id")
    if season_raw:
        queryset = queryset.filter(season_id=int(season_raw))
    return queryset


def _latest_sent_emails_by_practice(practice_ids):
    """Most recent sent scheduled email per practice (for reply tracking)."""
    practice_to_email = {}
    if not practice_ids:
        return practice_to_email
    emails = (
        ScheduledEmail.objects.filter(
            practices__in=practice_ids,
            task_completed_at__isnull=False,
        )
        .distinct()
        .prefetch_related("practices", "mentor_tokens__mentor")
        .order_by("-scheduled_send_at", "-id")
    )
    practice_id_set = set(practice_ids)
    for email in emails:
        for practice in email.practices.all():
            if practice.id in practice_id_set and practice.id not in practice_to_email:
                practice_to_email[practice.id] = email
    return practice_to_email


def build_mentor_non_response_report(practices):
    """Mentors on the latest sent email for each practice who have not submitted a reply."""
    practice_ids = [practice.id for practice in practices]
    practice_to_email = _latest_sent_emails_by_practice(practice_ids)
    email_ids = {email.id for email in practice_to_email.values()}

    replied_pairs = set()
    if email_ids:
        replied_pairs = set(
            ScheduledEmailMentorPracticeReply.objects.filter(
                mentor_token__scheduled_email_id__in=email_ids,
                practice_id__in=practice_ids,
            ).values_list("mentor_token_id", "practice_id")
        )

    report = []
    total_emailed = 0
    total_responded = 0
    for practice in practices:
        scheduled = practice_to_email.get(practice.id)
        pending = []
        mentors_emailed = 0
        mentors_responded = 0
        if scheduled is not None:
            tokens = list(scheduled.mentor_tokens.all())
            mentors_emailed = len(tokens)
            mentors_responded = sum(
                1 for token in tokens if (token.id, practice.id) in replied_pairs
            )
            total_emailed += mentors_emailed
            total_responded += mentors_responded
            for token in tokens:
                if (token.id, practice.id) in replied_pairs:
                    continue
                mentor = token.mentor
                pending.append(
                    {
                        "mentor_id": mentor.id,
                        "first_name": mentor.first_name,
                        "last_name": mentor.last_name,
                        "email": mentor.email,
                        "pace": mentor.pace,
                        "mentor_type": mentor.type,
                    }
                )
            pending.sort(
                key=lambda row: (
                    PACE_SORT.get(row["pace"], 99),
                    row["last_name"],
                    row["first_name"],
                )
            )
            response_pace_counts = email_response_pace_counts(
                tokens, replied_pairs, practice.id
            )
        else:
            response_pace_counts = [
                {
                    "pace": choice.value,
                    "emailed": 0,
                    "responded": 0,
                    "pending": 0,
                }
                for choice in PaceTypes
            ]

        report.append(
            {
                "id": practice.id,
                "date": practice.date.isoformat(),
                "nyrr_race": practice.nyrr_race or "",
                "season": practice.season_id,
                "season_year": practice.season.year,
                "full_practice": practice.full_practice,
                "scheduled_email_id": scheduled.id if scheduled else None,
                "scheduled_send_at": scheduled.scheduled_send_at.isoformat()
                if scheduled
                else None,
                "email_sent": scheduled is not None,
                "mentors_emailed": mentors_emailed,
                "mentors_responded": mentors_responded,
                "response_pace_counts": response_pace_counts,
                "pending_mentors": pending,
            }
        )
    return {
        "summary": {
            "mentors_emailed": total_emailed,
            "mentors_responded": total_responded,
        },
        "practices": report,
    }


class MentorNonResponseReportView(APIView):
    """Mentors who have not replied to practices on the latest sent mentor email."""

    def get(self, request):
        season_raw = (request.query_params.get("season") or "").strip()
        if season_raw:
            try:
                int(season_raw)
            except ValueError:
                return Response(
                    {"detail": "Invalid season id."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return Response(
            build_mentor_non_response_report(list(_practice_report_queryset(season_raw)))
        )


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


class SiteConfigView(APIView):
    """Public site config for the SPA (server timezone, etc.)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"time_zone": settings.TIME_ZONE})


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
        practice_list = list(practices)
        return Response(
            {
                "mentor": mentor_reply_payload(mentor),
                "season_year": season_year,
                "assigned_pace": assigned_pace or "",
                "scheduled_send_at": scheduled.scheduled_send_at.isoformat(),
                "practices": practice_payload,
                "pace_choices": [c.value for c in PaceTypes],
                "email_received_confirmed": mt.email_received_confirmed,
                "shows_partial_month": email_shows_partial_month(practice_list),
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
            pace = normalize_pace(item.get("pace") or "")
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

        mentor_pace_raw = request.data.get("mentor_pace")
        mentor_pace = (
            normalize_pace(mentor_pace_raw or "")
            if mentor_pace_raw is not None and str(mentor_pace_raw).strip()
            else ""
        )
        if mentor.type == MentorTypes.REMOTE:
            attending_any = any(
                att in ATTENDING_REPLY_VALUES
                for att in incoming_attendance.values()
            )
            if attending_any:
                if not mentor_pace:
                    return Response(
                        {
                            "detail": (
                                "Select your pace group for the practices "
                                "you plan to attend."
                            ),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if mentor_pace not in PACE_VALUES:
                    return Response(
                        {"detail": "Invalid pace choice."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                for pid, att in incoming_attendance.items():
                    if att in ATTENDING_REPLY_VALUES:
                        incoming_pace[pid] = mentor_pace

        rows = []
        for pid, att in incoming_attendance.items():
            practice = practices_by_id[pid]
            pace = normalize_pace(incoming_pace.get(pid) or "")
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
            if mentor.type == MentorTypes.REMOTE and mentor_pace:
                mentor.pace = mentor_pace
                mentor.save(update_fields=["pace", "updated_at"])
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
        .prefetch_related(
            "practices",
            "specific_mentors",
            Prefetch(
                "mentor_tokens",
                queryset=ScheduledEmailMentorToken.objects.prefetch_related(
                    "practice_replies"
                ),
            ),
        )
        .order_by("-scheduled_send_at", "-id")
    )
    serializer_class = ScheduledEmailSerializer

    def perform_create(self, serializer):
        instance = serializer.save()
        instance.sync_mentor_tokens()

    def perform_update(self, serializer):
        instance = serializer.save()
        if not instance.task_completed_at:
            instance.sync_mentor_tokens()

    @action(detail=True, methods=["post"], url_path="send-now")
    def send_now(self, request, pk=None):
        scheduled = self.get_object()
        if scheduled.task_completed_at:
            return Response(
                {"detail": "This email has already been sent."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        dry_run = (
            request.data.get("dry_run") is True
            if isinstance(request.data, dict)
            else False
        )
        try:
            result = send_scheduled_email_now(scheduled, dry_run=dry_run)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ConnectionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(result)

    @action(detail=True, methods=["get"], url_path="pending-mentors")
    def pending_mentors(self, request, pk=None):
        """Mentors who have not yet replied to this sent email."""
        scheduled = self.get_object()
        if not scheduled.task_completed_at:
            return Response(
                {
                    "detail": (
                        "Pending mentors are only available after the email has been sent."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        email = ScheduledEmail.objects.get(pk=scheduled.pk)
        stats = email.reply_stats()
        pending = stats.get("pending_mentors")
        if not isinstance(pending, list):
            pending = ScheduledEmail.serialize_pending_mentor_rows(
                email.query_pending_mentors()
            )
        return Response(
            {
                "count": len(pending),
                "pending_mentor_ids": stats.get("pending_mentor_ids") or [],
                "pending_mentors": pending,
            }
        )

    @action(detail=True, methods=["post"], url_path="send-reply-reminders")
    def send_reply_reminders(self, request, pk=None):
        scheduled = self.get_object()
        if not scheduled.task_completed_at:
            return Response(
                {
                    "detail": (
                        "Reply reminders can only be sent after the email has been sent."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        dry_run = (
            request.data.get("dry_run") is True
            if isinstance(request.data, dict)
            else False
        )
        try:
            result = send_reply_reminders_for_email(scheduled, dry_run=dry_run)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ConnectionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(result)


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
