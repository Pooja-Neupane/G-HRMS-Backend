"""Transactional, append-only document verification workflow."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from documents.exceptions import (
    DocumentConflictError,
    DocumentValidationError,
    DocumentVersionNotFoundError,
)
from documents.models import DocumentVerification, DocumentVersion
from documents.repositories import (
    DocumentVerificationRepository,
    DocumentVersionRepository,
)


class DocumentVerificationService:
    def __init__(
        self,
        *,
        version_repository=None,
        verification_repository=None,
    ):
        self.version_repository = (
            version_repository or DocumentVersionRepository()
        )
        self.verification_repository = (
            verification_repository or DocumentVerificationRepository()
        )

    def record_decision(
        self,
        *,
        version_id,
        decision,
        remarks="",
        checklist=None,
        actor,
    ):
        try:
            with transaction.atomic():
                try:
                    version = self.version_repository.get_for_update(
                        version_id
                    )
                except self.version_repository.model.DoesNotExist as exc:
                    raise DocumentVersionNotFoundError() from exc

                verification = DocumentVerification(
                    version=version,
                    decision=decision,
                    reviewed_by=actor,
                    file_hash_sha256=version.file_hash_sha256,
                    remarks=remarks or "",
                    checklist=checklist or {},
                )
                self._validate(verification)
                self.verification_repository.save(verification)

                version.verification_status = (
                    DocumentVersion.VerificationStatus.VERIFIED
                    if decision == DocumentVerification.Decision.VERIFIED
                    else DocumentVersion.VerificationStatus.REJECTED
                )
                version.save(
                    update_fields=["verification_status", "row_version"]
                )
                return verification
        except IntegrityError as exc:
            raise DocumentConflictError() from exc

    @staticmethod
    def _validate(verification):
        try:
            verification.full_clean()
        except ValidationError as exc:
            details = (
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            )
            raise DocumentValidationError(details) from exc
