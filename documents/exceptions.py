"""Framework-independent document workflow errors."""

from core.errors import ApplicationError

class DocumentError(ApplicationError):
    code = "document_error"
    message = "The document operation could not be completed."

class DocumentNotFoundError(DocumentError):
    code = "document_not_found"
    message = "The requested document was not found."
    status_code = 404

class DocumentVersionNotFoundError(DocumentError):
    code = "document_version_not_found"
    message = "The requested version was not found."
    status_code = 404

class DocumentValidationError(DocumentError):
    code="document_validation_error"
    message="The document data is invalid."
    status_code = 400

    def __init__(self, details):
        super().__init__(self.message, details=details)

class DocumentConflictError(DocumentError):
    code="document_conflict"
    message="The document operation conflicts with its current state."
    status_code=409

class DocumentVerificationError(DocumentError):
    code="document_verification_error"
    message="The document cannot be verified in its current state."
    status_code=409

class DocumentUploadNotAllowedError(DocumentError):
    code = "document_upload_not_allowed"
    message = "You are not allowed to upload this document."
    status_code = 403