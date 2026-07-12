"""Scan document versions that have not yet been scanned (or whose scan failed).

Run on a schedule or after the clamd daemon recovers:

    python manage.py scan_pending_versions
    python manage.py scan_pending_versions --include-failed
"""

from django.core.management.base import BaseCommand

from documents.models import DocumentVersion
from documents.scanning import get_scanner
from documents.services import DocumentScanService


class Command(BaseCommand):
    help = "Scan PENDING (and optionally FAILED) document versions with ClamAV."

    def add_arguments(self, parser):
        parser.add_argument(
            "--include-failed",
            action="store_true",
            help="Also re-scan versions whose previous scan FAILED.",
        )

    def handle(self, *args, **options):
        scanner = get_scanner()
        if scanner is None:
            self.stdout.write(
                "Document scanning is disabled (DOCUMENT_SCAN_ENABLED=False)."
            )
            return

        statuses = [DocumentVersion.ScanStatus.PENDING]
        if options["include_failed"]:
            statuses.append(DocumentVersion.ScanStatus.FAILED)

        versions = DocumentVersion.objects.filter(scan_status__in=statuses)
        service = DocumentScanService()

        counts = {
            DocumentVersion.ScanStatus.CLEAN: 0,
            DocumentVersion.ScanStatus.INFECTED: 0,
            DocumentVersion.ScanStatus.FAILED: 0,
        }
        for version_id in list(versions.values_list("id", flat=True)):
            scanned = service.scan_version(
                version_id=version_id, scanner=scanner
            )
            counts[scanned.scan_status] += 1

        total = sum(counts.values())
        self.stdout.write(
            self.style.SUCCESS(
                f"Scanned {total} version(s): "
                f"{counts[DocumentVersion.ScanStatus.CLEAN]} clean, "
                f"{counts[DocumentVersion.ScanStatus.INFECTED]} infected, "
                f"{counts[DocumentVersion.ScanStatus.FAILED]} failed."
            )
        )
