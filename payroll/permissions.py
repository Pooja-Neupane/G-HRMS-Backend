from rest_framework.permissions import SAFE_METHODS

from account.models import ModuleKey
from employees.permissions import EmployeePermission


class PayrollPermission(EmployeePermission):
    """HR or superadmin access to payroll workflow.

    This keeps payroll aligned with the existing read/write policy used by the
    employee APIs instead of forcing a separate `RoleModuleAccess` record for
    every role instance in the test environment.
    """

    module_key = ModuleKey.PAYROLL

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
