"""Authorization policy for organization catalog administration."""

from rest_framework.permissions import BasePermission, SAFE_METHODS


class OrganizationCatalogPermission(BasePermission):
    """Authenticated reads; superadmin-only catalog mutations."""

    message = "Superadmin privileges are required to modify organization data."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(user.is_superuser or user.role == user.Role.SUPERADMIN)
