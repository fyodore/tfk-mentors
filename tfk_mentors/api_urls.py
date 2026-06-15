from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CoachViewSet,
    CoachPracticeAssignmentViewSet,
    MentorPracticeAssignmentViewSet,
    MentorScheduledEmailReplyView,
    MentorViewSet,
    PracticeRosterReportView,
    MentorNonResponseReportView,
    PracticeViewSet,
    RequestsViewSet,
    ScheduledEmailViewSet,
    SeasonViewSet,
    SiteAuthView,
    SiteConfigView,
    TfkStaffViewSet,
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
router.register("requests", RequestsViewSet, basename="requests")
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
    path("", include(router.urls)),
]
