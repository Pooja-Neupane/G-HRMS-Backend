"""Authorization policy for employee document APIs."""

from rest_framework.permissions import BasePermission, SAFE_METHODS


class DocumentPermission(BasePermission):
    """Authenticated reads; HR personnel and superadmins may mutate.

    Finer-grained upload rules (category policy, upload source) are enforced
    by the upload service, which raises ``DocumentUploadNotAllowedError``.
    """

    message = "HR personnel or superadmin privileges are required for this action."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(
            user.is_superuser
            or user.role in {user.Role.SUPERADMIN, user.Role.HR_PERSONNEL}
        )
