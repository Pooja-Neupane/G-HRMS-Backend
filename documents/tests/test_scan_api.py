import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from documents.models import (
    DocumentCategory,
    DocumentVerification,
    DocumentVersion,
    EmployeeDocument,
)
from documents.services import DocumentUploadService
from employees.models import Employee


User = get_user_model()


class DocumentScanAPITests(APITestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory.name
        )
        self.settings_override.enable()

        # The scan endpoint is superadmin-only (scanner callback / admin
        # override); verification is allowed for HR and superadmins alike.
        self.hr_user = User.objects.create_user(
            username="hr-scan",
            email="hr-scan@example.com",
            password="StrongPassword@123",
            role=User.Role.SUPERADMIN,
            status=User.Status.ACTIVE,
        )
        self.employee = Employee.objects.create(
            first_name="Document",
            last_name="Owner",
            ka_sa_num="EMP-SCAN-001",
            dob_bs="2050-01-01",
            dob_ad=date(1993, 4, 14),
            jobstartdate_bs="2080-01-01",
            jobstartdate_ad=date(2023, 4, 14),
            current_position_date_bs="2080-01-01",
            current_position_date_ad=date(2023, 4, 14),
            email="scan-owner@example.com",
        )
        self.category = DocumentCategory.objects.create(
            code="DOC-SCAN",
            name="Scan Test",
            allowed_extensions=["pdf"],
            max_file_size_mb=2,
        )
        self.document = EmployeeDocument.objects.create(
            code="EMP-DOC-SCAN",
            employee=self.employee,
            category=self.category,
            title="Scan Test",
        )
        self.version = DocumentUploadService().upload_new_version(
            document_id=self.document.id,
            uploaded_file=SimpleUploadedFile(
                "document.pdf", b"content", content_type="application/pdf"
            ),
            upload_source=DocumentVersion.UploadSource.HR,
            actor=self.hr_user,
        )
        self.scan_url = reverse("document-version-scan", args=[self.version.id])
        self.verify_url = reverse(
            "document-version-verify", args=[self.version.id]
        )

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()

    def test_recording_clean_scan_updates_status(self):
        self.client.force_authenticate(self.hr_user)

        response = self.client.post(
            self.scan_url,
            {"scan_status": DocumentVersion.ScanStatus.CLEAN},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["scan_status"], DocumentVersion.ScanStatus.CLEAN
        )
        self.version.refresh_from_db()
        self.assertEqual(
            self.version.scan_status, DocumentVersion.ScanStatus.CLEAN
        )

    def test_pending_is_not_a_recordable_result(self):
        self.client.force_authenticate(self.hr_user)

        response = self.client.post(
            self.scan_url,
            {"scan_status": DocumentVersion.ScanStatus.PENDING},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_scan_is_rejected(self):
        response = self.client.post(
            self.scan_url,
            {"scan_status": DocumentVersion.ScanStatus.CLEAN},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_hr_cannot_record_scan_result(self):
        hr_only = User.objects.create_user(
            username="hr-only-scan",
            email="hr-only-scan@example.com",
            password="StrongPassword@123",
            role=User.Role.HR_PERSONNEL,
            status=User.Status.ACTIVE,
        )
        self.client.force_authenticate(hr_only)

        response = self.client.post(
            self.scan_url,
            {"scan_status": DocumentVersion.ScanStatus.CLEAN},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_clean_scan_then_verify_succeeds_end_to_end(self):
        self.client.force_authenticate(self.hr_user)

        scan_response = self.client.post(
            self.scan_url,
            {"scan_status": DocumentVersion.ScanStatus.CLEAN},
            format="json",
        )
        verify_response = self.client.post(
            self.verify_url,
            {"decision": DocumentVerification.Decision.VERIFIED},
            format="json",
        )

        self.assertEqual(scan_response.status_code, status.HTTP_200_OK)
        self.assertEqual(verify_response.status_code, status.HTTP_201_CREATED)
        self.version.refresh_from_db()
        self.assertEqual(
            self.version.verification_status,
            DocumentVersion.VerificationStatus.VERIFIED,
        )

    def test_infected_scan_blocks_verification(self):
        self.client.force_authenticate(self.hr_user)

        self.client.post(
            self.scan_url,
            {"scan_status": DocumentVersion.ScanStatus.INFECTED},
            format="json",
        )
        verify_response = self.client.post(
            self.verify_url,
            {"decision": DocumentVerification.Decision.VERIFIED},
            format="json",
        )

        self.assertEqual(
            verify_response.status_code, status.HTTP_400_BAD_REQUEST
        )
        self.version.refresh_from_db()
        self.assertEqual(
            self.version.verification_status,
            DocumentVersion.VerificationStatus.PENDING,
        )
