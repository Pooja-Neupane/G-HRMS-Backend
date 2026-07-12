"""DRF permission classes for the authentication app."""

from rest_framework.permissions import BasePermission


class IsSuperAdmin(BasePermission):
    """Allow only authenticated SUPERADMIN (or Django superuser) accounts."""

    message = "Superadmin privileges are required for this action."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return bool(user.is_superuser or user.role == user.Role.SUPERADMIN)
