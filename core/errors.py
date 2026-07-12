"""Framework-independent application erros."""

class ApplicationError(Exception):
    """Base class for expected business-rule failures."""

    code = "application_error"
    message = "The operation could not be completed."
    status_code = 400

    def __init__(self, message=None,*,details=None):
        self.message = message or self.message
        self.details = details
        super().__init__(self.message)