"""Framework-independent employee workflow errors."""

from core.errors import ApplicationError


class EmployeeNotFoundError(ApplicationError):
    code = "employee_not_found"
    message = "The requested employee was not found."
    status_code = 404


class EmployeeConflictError(ApplicationError):
    code = "employee_conflict"
    message = "An employee with one of these unique identifiers already exists."
    status_code = 409


class EmployeeValidationError(ApplicationError):
    code = "employee_validation_error"
    message = "The employee data is invalid."
    status_code = 400

    def __init__(self, details):
        super().__init__(self.message, details=details)


class EmployeeInUseError(ApplicationError):
    code = "employee_in_use"
    message = "The employee cannot be deactivated while assigned to active duties."
    status_code = 409

    def __init__(self, dependencies):
        super().__init__(self.message, details={"dependencies": dependencies})
