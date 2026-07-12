import tempfile
from datetime import date
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from documents.models import (
    DocumentCategory,
    DocumentVersion,
    EmployeeDocument,
)
from documents.scanning import ClamAVScanner, ScanOutcome, get_scanner
from documents.services import DocumentScanService, DocumentUploadService
from employees.models import Employee


User = get_user_model()


class _FakeClamd:
    def __init__(self, *, response=None, raises=None):
        self.response = response
        self.raises = raises

    def instream(self, fileobj):
        if self.raises is not None:
            raise self.raises
        return self.response


def _scanner_returning(client):
    scanner = ClamAVScanner(host="x", port=0, timeout=1.0)
    scanner._client = lambda: client
    return scanner


class ClamAVScannerMappingTests(TestCase):
    def test_ok_maps_to_clean(self):
        scanner = _scanner_returning(
            _FakeClamd(response={"stream": ("OK", None)})
        )
        outcome = scanner.scan(BytesIO(b"safe"))
        self.assertEqual(outcome.status, DocumentVersion.ScanStatus.CLEAN)

    def test_found_maps_to_infected_with_signature(self):
        scanner = _scanner_returning(
            _FakeClamd(response={"stream": ("FOUND", "Eicar-Test-Signature")})
        )
        outcome = scanner.scan(BytesIO(b"virus"))
        self.assertEqual(outcome.status, DocumentVersion.ScanStatus.INFECTED)
        self.assertEqual(outcome.signature, "Eicar-Test-Signature")

    def test_transport_error_maps_to_failed(self):
        scanner = _scanner_returning(
            _FakeClamd(raises=ConnectionError("daemon down"))
        )
        outcome = scanner.scan(BytesIO(b"x"))
        self.assertEqual(outcome.status, DocumentVersion.ScanStatus.FAILED)


class GetScannerTests(TestCase):
    @override_settings(DOCUMENT_SCAN_ENABLED=False)
    def test_returns_none_when_disabled(self):
        self.assertIsNone(get_scanner())

    @override_settings(
        DOCUMENT_SCAN_ENABLED=True,
        CLAMAV_UNIX_SOCKET="",
        CLAMAV_HOST="127.0.0.1",
        CLAMAV_PORT=3310,
        CLAMAV_TIMEOUT=5.0,
    )
    def test_returns_scanner_when_enabled(self):
        self.assertIsInstance(get_scanner(), ClamAVScanner)


class _StubScanner:
    def __init__(self, outcome):
        self.outcome = outcome
        self.scanned = False

    def scan(self, fileobj):
        self.scanned = True
        return self.outcome


class ScanVersionServiceTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory.name
        )
        self.settings_override.enable()

        self.actor = User.objects.create_user(
            username="scanner-actor",
            email="scanner-actor@example.com",
            password="StrongPassword@123",
            role=User.Role.HR_PERSONNEL,
            status=User.Status.ACTIVE,
        )
        self.employee = Employee.objects.create(
            first_name="Scan",
            last_name="Owner",
            ka_sa_num="EMP-SCANSVC-001",
            dob_bs="2050-01-01",
            dob_ad=date(1993, 4, 14),
            jobstartdate_bs="2080-01-01",
            jobstartdate_ad=date(2023, 4, 14),
            current_position_date_bs="2080-01-01",
            current_position_date_ad=date(2023, 4, 14),
            email="scansvc-owner@example.com",
        )
        self.category = DocumentCategory.objects.create(
            code="DOC-SCANSVC",
            name="Scan Service Test",
            allowed_extensions=["pdf"],
            max_file_size_mb=2,
        )
        self.document = EmployeeDocument.objects.create(
            code="EMP-DOC-SCANSVC",
            employee=self.employee,
            category=self.category,
            title="Scan Service Test",
        )
        self.version = DocumentUploadService().upload_new_version(
            document_id=self.document.id,
            uploaded_file=SimpleUploadedFile(
                "document.pdf", b"content", content_type="application/pdf"
            ),
            upload_source=DocumentVersion.UploadSource.HR,
            actor=self.actor,
        )

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()

    def test_clean_outcome_records_clean_status(self):
        scanner = _StubScanner(ScanOutcome(DocumentVersion.ScanStatus.CLEAN))

        result = DocumentScanService().scan_version(
            version_id=self.version.id, scanner=scanner
        )

        self.assertTrue(scanner.scanned)
        self.assertEqual(result.scan_status, DocumentVersion.ScanStatus.CLEAN)
        self.version.refresh_from_db()
        self.assertEqual(
            self.version.scan_status, DocumentVersion.ScanStatus.CLEAN
        )

    def test_infected_outcome_records_infected_status(self):
        scanner = _StubScanner(
            ScanOutcome(DocumentVersion.ScanStatus.INFECTED, signature="X")
        )

        DocumentScanService().scan_version(
            version_id=self.version.id, scanner=scanner
        )

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.scan_status, DocumentVersion.ScanStatus.INFECTED
        )

    @override_settings(DOCUMENT_SCAN_ENABLED=False)
    def test_disabled_scanner_is_a_noop(self):
        result = DocumentScanService().scan_version(version_id=self.version.id)

        self.assertIsNone(result)
        self.version.refresh_from_db()
        self.assertEqual(
            self.version.scan_status, DocumentVersion.ScanStatus.PENDING
        )
