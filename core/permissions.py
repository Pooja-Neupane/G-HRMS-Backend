from rest_framework.permissions import BasePermission

class HasModuleAccess(BasePermission):
    """
        Allow only if the user's role may open the view's module.
        set `module_key = "payroll"` (etc.) on the viewSet
    """
    message = "Your role does not have access to this module."

    def has_permission(self, request, view):
        module = getattr(view,"module_key",None)
        if module is None:
            return True
        return bool(request.user and request.user.is_authenticated
                     and request.user.can_access_module(module))
    

class HasPermissionCode(BasePermission):
    """
        Allow only if the user holds a 'resource:action' permission.Map per
        HTTP method on the view via `required_perms={"POST":"employee:create"}`.
    """

    message = "You don't have permission to perform this action."

    def has_permission(self, request, view):
        required = getattr(view,"required_perms",{})
        code = required.get(request.method)
        if not code:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.has_perm_code(code))