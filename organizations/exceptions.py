"""Framework-independent errors for organization catalog workflows."""

from core.errors import ApplicationError


class OrganizationCatalogError(ApplicationError):
    code = "organization_catalog_error"
    message = "The organization catalog operation could not be completed."


class ResourceNotFoundError(OrganizationCatalogError):
    status_code = 404

    def __init__(self, resource: str):
        self.code = f"{resource}_not_found"
        super().__init__(f"The requested {resource.replace('_', ' ')} was not found.")


class ResourceInUseError(OrganizationCatalogError):
    code = "resource_in_use"
    status_code = 409

    def __init__(self, resource: str, dependencies: list[str]):
        super().__init__(
            f"The {resource.replace('_', ' ')} cannot be deleted while it is in use.",
            details={"dependencies": dependencies},
        )


class ResourceConflictError(OrganizationCatalogError):
    code = "resource_conflict"
    status_code = 409

    def __init__(self, resource: str):
        super().__init__(
            f"A conflicting {resource.replace('_', ' ')} already exists."
        )


class ResourceValidationError(OrganizationCatalogError):
    code = "resource_validation_error"
    status_code = 400

    def __init__(self, details):
        super().__init__("The organization catalog data is invalid.", details=details)
