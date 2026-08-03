from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CoachViewSet,
    CoachPracticeAssignmentViewSet,
    MentorCellPhoneRequestViewSet,
    MentorCellPhoneUpdateView,
    MentorPracticeAssignmentViewSet,
    MentorScheduledEmailReplyView,
    MentorViewSet,
    PracticeAttendanceArchiveView,
    PracticeAttendanceCurrentView,
    PracticeAttendanceDetailView,
    PracticeRosterReportView,
    MentorNonResponseReportView,
    MentorScheduleView,
    PublicMentorDirectoryView,
    PublicMentorDirectoryPracticesView,
    PublicPracticeMentorRosterView,
    PublicPracticeSwapOptionsView,
    PublicMentorSwapRequestCreateView,
    PublicMentorSwapRequestDetailView,
    PublicMentorSwapRequestApproveView,
    PublicMentorSwapRequestRejectView,
    PublicUpcomingPracticesView,
    MentorSwapReportView,
    PracticeViewSet,
    PracticeReminderEmailViewSet,
    RequestsViewSet,
    ScheduledEmailViewSet,
    SeasonViewSet,
    SiteAuthView,
    SiteConfigView,
    TfkStaffViewSet,
    UnderfilledPaceMentorEmailViewSet,
    UnderfilledPaceMentorReplyView,
)

router = DefaultRouter()
router.register("season", SeasonViewSet, basename="season")
router.register("tfk-staff", TfkStaffViewSet, basename="tfk-staff")
router.register("coach", CoachViewSet, basename="coach")
router.register(
    "coach-practice-assignment",
    CoachPracticeAssignmentViewSet,
    basename="coach-practice-assignment",
)
router.register(
    "mentor-practice-assignment",
    MentorPracticeAssignmentViewSet,
    basename="mentor-practice-assignment",
)
router.register("mentor", MentorViewSet, basename="mentor")
router.register("practice", PracticeViewSet, basename="practice")
router.register(
    "practice-reminder-email",
    PracticeReminderEmailViewSet,
    basename="practice-reminder-email",
)
router.register("requests", RequestsViewSet, basename="requests")
router.register(
    "mentor-cell-phone-request",
    MentorCellPhoneRequestViewSet,
    basename="mentor-cell-phone-request",
)
router.register(
    "underfilled-pace-email",
    UnderfilledPaceMentorEmailViewSet,
    basename="underfilled-pace-email",
)
router.register(
    "scheduled-email",
    ScheduledEmailViewSet,
    basename="scheduled-email",
)

urlpatterns = [
    path(
        "scheduled-email/<int:pk>/pending-mentors/",
        ScheduledEmailViewSet.as_view({"get": "pending_mentors"}),
        name="scheduled-email-pending-mentors",
    ),
    path("config/", SiteConfigView.as_view(), name="site-config"),
    path("auth/session/", SiteAuthView.as_view(), name="site-auth"),
    path(
        "reports/practice-roster/",
        PracticeRosterReportView.as_view(),
        name="practice-roster-report",
    ),
    path(
        "reports/mentor-non-responses/",
        MentorNonResponseReportView.as_view(),
        name="mentor-non-response-report",
    ),
    path(
        "practices/schedule-mentors/",
        MentorScheduleView.as_view(),
        name="mentor-schedule",
    ),
    path(
        "mentor-email-reply/",
        MentorScheduledEmailReplyView.as_view(),
        name="mentor-email-reply-query",
    ),
    path(
        "mentor-email-reply/<uuid:token>/",
        MentorScheduledEmailReplyView.as_view(),
        name="mentor-email-reply",
    ),
    path(
        "mentor-cell-phone-update/",
        MentorCellPhoneUpdateView.as_view(),
        name="mentor-cell-phone-update-query",
    ),
    path(
        "mentor-cell-phone-update/<uuid:token>/",
        MentorCellPhoneUpdateView.as_view(),
        name="mentor-cell-phone-update",
    ),
    path(
        "underfilled-pace-reply/",
        UnderfilledPaceMentorReplyView.as_view(),
        name="underfilled-pace-reply-query",
    ),
    path(
        "underfilled-pace-reply/<uuid:token>/",
        UnderfilledPaceMentorReplyView.as_view(),
        name="underfilled-pace-reply",
    ),
    path(
        "practice/<int:pk>/mentor-replies/",
        PracticeViewSet.as_view(
            {
                "get": "mentor_replies",
                "post": "mentor_replies",
                "patch": "mentor_replies",
                "delete": "mentor_replies",
            }
        ),
        name="practice-mentor-replies",
    ),
    path(
        "practice-attendance/current/",
        PracticeAttendanceCurrentView.as_view(),
        name="practice-attendance-current",
    ),
    path(
        "practice-attendance/archived/",
        PracticeAttendanceArchiveView.as_view(),
        name="practice-attendance-archived",
    ),
    path(
        "practice-attendance/<int:pk>/",
        PracticeAttendanceDetailView.as_view(),
        name="practice-attendance-detail",
    ),
    path(
        "public/mentor-directory/",
        PublicMentorDirectoryView.as_view(),
        name="public-mentor-directory",
    ),
    path(
        "public/mentor-directory/<int:pk>/practices/",
        PublicMentorDirectoryPracticesView.as_view(),
        name="public-mentor-directory-practices",
    ),
    path(
        "public/practices/upcoming/",
        PublicUpcomingPracticesView.as_view(),
        name="public-upcoming-practices",
    ),
    path(
        "public/practice/<int:pk>/mentors/",
        PublicPracticeMentorRosterView.as_view(),
        name="public-practice-mentor-roster",
    ),
    path(
        "public/practice/<int:pk>/swap-options/",
        PublicPracticeSwapOptionsView.as_view(),
        name="public-practice-swap-options",
    ),
    path(
        "public/mentor-swap-request/",
        PublicMentorSwapRequestCreateView.as_view(),
        name="public-mentor-swap-request-create",
    ),
    path(
        "public/mentor-swap-request/<uuid:token>/",
        PublicMentorSwapRequestDetailView.as_view(),
        name="public-mentor-swap-request-detail",
    ),
    path(
        "public/mentor-swap-request/<uuid:token>/approve/",
        PublicMentorSwapRequestApproveView.as_view(),
        name="public-mentor-swap-request-approve",
    ),
    path(
        "public/mentor-swap-request/<uuid:token>/reject/",
        PublicMentorSwapRequestRejectView.as_view(),
        name="public-mentor-swap-request-reject",
    ),
    path(
        "reports/mentor-swaps/",
        MentorSwapReportView.as_view(),
        name="mentor-swap-report",
    ),
    path("", include(router.urls)),
]
