"""Transactional document upload and version-rotation workflow."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from documents.exceptions import (
    DocumentConflictError,
    DocumentNotFoundError,
    DocumentUploadNotAllowedError,
    DocumentValidationError,
)
from documents.models import DocumentCategory, DocumentVersion, EmployeeDocument
from documents.repositories import (
    DocumentVersionRepository,
    EmployeeDocumentRepository,
)
from documents.utils import inspect_uploaded_file


class DocumentUploadService:
    def __init__(
        self,
        *,
        document_repository=None,
        version_repository=None,
    ):
        self.document_repository = (
            document_repository or EmployeeDocumentRepository()
        )
        self.version_repository = (
            version_repository or DocumentVersionRepository()
        )

    def upload_new_version(
        self,
        *,
        document_id,
        uploaded_file,
        upload_source,
        actor=None,
    ):
        metadata = inspect_uploaded_file(uploaded_file)
        version = None

        try:
            with transaction.atomic():
                try:
                    document = self.document_repository.get_for_update(
                        document_id
                    )
                except self.document_repository.model.DoesNotExist as exc:
                    raise DocumentNotFoundError() from exc

                self._validate_upload_policy(
                    document=document,
                    upload_source=upload_source,
                )

                current_version = (
                    self.version_repository.get_current_for_update(
                        document.id
                    )
                )
                version_number = (
                    self.version_repository.next_version_number(document.id)
                )

                verification_status = (
                    DocumentVersion.VerificationStatus.NOT_REQUIRED
                    if document.category.verification_mode
                    == DocumentCategory.VerificationMode.NOT_REQUIRED
                    else DocumentVersion.VerificationStatus.PENDING
                )

                version = DocumentVersion(
                    document=document,
                    version_number=version_number,
                    file=uploaded_file,
                    original_file_name=metadata.original_file_name,
                    content_type=metadata.content_type,
                    file_size_bytes=metadata.file_size_bytes,
                    file_hash_sha256=metadata.file_hash_sha256,
                    upload_source=upload_source,
                    uploaded_by=(
                        actor
                        if actor is not None
                        and getattr(actor, "is_authenticated", False)
                        else None
                    ),
                    verification_status=verification_status,
                    scan_status=DocumentVersion.ScanStatus.PENDING,
                    is_current=True,
                )

                self._assign_actor(version, actor)

                if current_version is not None:
                    self.version_repository.mark_not_current(current_version)

                self._validate(version)
                self.version_repository.save(version)
                self._schedule_scan(version.id)
                return version

        except IntegrityError as exc:
            self._delete_stored_file(version)
            raise DocumentConflictError() from exc
        except Exception:
            self._delete_stored_file(version)
            raise

    @staticmethod
    def _schedule_scan(version_id):
        """After the upload commits, scan the stored file out of band.

        Gated by DOCUMENT_SCAN_ON_UPLOAD. The scan runs only once the file and
        row are durably committed; a scanner failure records FAILED and never
        rolls back the upload. Imported locally to avoid an import cycle.
        """
        if not getattr(settings, "DOCUMENT_SCAN_ON_UPLOAD", False):
            return

        def _run():
            from documents.services.scans import DocumentScanService

            DocumentScanService().scan_version(version_id=version_id)

        transaction.on_commit(_run)

    @staticmethod
    def _validate_upload_policy(*, document, upload_source):
        if document.lifecycle_status != EmployeeDocument.LifecycleStatus.ACTIVE:
            raise DocumentConflictError(
                "Only active documents can receive new versions."
            )

        if not document.category.is_active:
            raise DocumentValidationError(
                {"category": ["The document category is inactive."]}
            )

        if (
            upload_source == DocumentVersion.UploadSource.EMPLOYEE
            and not document.category.employee_can_upload
        ):
            raise DocumentUploadNotAllowedError()

    @staticmethod
    def _assign_actor(version, actor):
        if actor is None or not getattr(actor, "is_authenticated", False):
            return

        version.created_by = actor
        version.updated_by = actor

    @staticmethod
    def _validate(version):
        try:
            version.full_clean()
        except ValidationError as exc:
            details = (
                exc.message_dict
                if hasattr(exc, "message_dict")
                else exc.messages
            )
            raise DocumentValidationError(details) from exc

    @staticmethod
    def _delete_stored_file(version):
        if version is None:
            return

        stored_file = version.file
        if (
            stored_file
            and stored_file.name
            and getattr(stored_file, "_committed", False)
        ):
            stored_file.storage.delete(stored_file.name)