from rest_framework.permissions import BasePermission


class IsSiteAuthenticated(BasePermission):
    """Requires a valid site password login stored in the session."""

    message = "Authentication required."

    def has_permission(self, request, view):
        return request.session.get("site_authenticated") is True
