"""Records malware-scan outcomes against an immutable file version.

This is the boundary a scanner (e.g. ClamAV) calls back into once it finishes
inspecting an uploaded file. Scanning itself is performed out of band; this
service only persists the resulting status transition.
"""

from django.db import transaction

from documents.exceptions import (
    DocumentValidationError,
    DocumentVersionNotFoundError,
)
from documents.models import DocumentVersion
from documents.repositories import DocumentVersionRepository
from documents.scanning import get_scanner


class DocumentScanService:
    # PENDING is the initial state and cannot be recorded as a scan result.
    RECORDABLE_STATUSES = frozenset(
        {
            DocumentVersion.ScanStatus.CLEAN,
            DocumentVersion.ScanStatus.INFECTED,
            DocumentVersion.ScanStatus.FAILED,
        }
    )

    def __init__(self, *, version_repository=None):
        self.version_repository = (
            version_repository or DocumentVersionRepository()
        )

    def record_result(self, *, version_id, scan_status, actor=None):
        if scan_status not in self.RECORDABLE_STATUSES:
            raise DocumentValidationError(
                {"scan_status": ["Provide a completed scan result."]}
            )

        with transaction.atomic():
            try:
                version = self.version_repository.get_for_update(version_id)
            except self.version_repository.model.DoesNotExist as exc:
                raise DocumentVersionNotFoundError() from exc

            version.scan_status = scan_status
            version.save(update_fields=["scan_status", "row_version"])
            return version

    def scan_version(self, *, version_id, scanner=None):
        """Run the configured scanner over a version's file and record it.

        Returns the updated version, or None when scanning is disabled.
        """
        if scanner is None:
            scanner = get_scanner()
        if scanner is None:
            return None

        version = self.version_repository.get_by_id(version_id)
        if version is None:
            raise DocumentVersionNotFoundError()

        version.file.open("rb")
        try:
            outcome = scanner.scan(version.file)
        finally:
            version.file.close()

        return self.record_result(
            version_id=version_id, scan_status=outcome.status
        )
