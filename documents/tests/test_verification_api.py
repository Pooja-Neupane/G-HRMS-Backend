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


class DocumentVerificationAPITests(APITestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory.name
        )
        self.settings_override.enable()

        self.hr_user = User.objects.create_user(
            username="hr-verify",
            email="hr-verify@example.com",
            password="StrongPassword@123",
            role=User.Role.HR_PERSONNEL,
            status=User.Status.ACTIVE,
        )
        self.employee = Employee.objects.create(
            first_name="Document",
            last_name="Owner",
            ka_sa_num="EMP-VERIFY-001",
            dob_bs="2050-01-01",
            dob_ad=date(1993, 4, 14),
            jobstartdate_bs="2080-01-01",
            jobstartdate_ad=date(2023, 4, 14),
            current_position_date_bs="2080-01-01",
            current_position_date_ad=date(2023, 4, 14),
            email="verify-owner@example.com",
        )
        self.category = DocumentCategory.objects.create(
            code="DOC-VERIFY",
            name="Verify Test",
            allowed_extensions=["pdf"],
            max_file_size_mb=2,
        )
        self.document = EmployeeDocument.objects.create(
            code="EMP-DOC-VERIFY",
            employee=self.employee,
            category=self.category,
            title="Verify Test",
        )
        self.version = DocumentUploadService().upload_new_version(
            document_id=self.document.id,
            uploaded_file=SimpleUploadedFile(
                "document.pdf", b"content", content_type="application/pdf"
            ),
            upload_source=DocumentVersion.UploadSource.HR,
            actor=self.hr_user,
        )
        self.verify_url = reverse(
            "document-version-verify", args=[self.version.id]
        )

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()

    def mark_scan_clean(self):
        self.version.scan_status = DocumentVersion.ScanStatus.CLEAN
        self.version.save(update_fields=["scan_status", "row_version"])

    def test_verify_clean_version_marks_it_verified(self):
        self.mark_scan_clean()
        self.client.force_authenticate(self.hr_user)

        response = self.client.post(
            self.verify_url,
            {"decision": DocumentVerification.Decision.VERIFIED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.version.refresh_from_db()
        self.assertEqual(
            self.version.verification_status,
            DocumentVersion.VerificationStatus.VERIFIED,
        )
        self.assertEqual(
            DocumentVerification.objects.filter(version=self.version).count(), 1
        )

    def test_cannot_verify_without_clean_scan(self):
        self.client.force_authenticate(self.hr_user)

        response = self.client.post(
            self.verify_url,
            {"decision": DocumentVerification.Decision.VERIFIED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.version.refresh_from_db()
        self.assertEqual(
            self.version.verification_status,
            DocumentVersion.VerificationStatus.PENDING,
        )

    def test_rejection_requires_remarks(self):
        self.client.force_authenticate(self.hr_user)

        response = self.client.post(
            self.verify_url,
            {"decision": DocumentVerification.Decision.REJECTED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejection_with_remarks_marks_version_rejected(self):
        self.client.force_authenticate(self.hr_user)

        response = self.client.post(
            self.verify_url,
            {
                "decision": DocumentVerification.Decision.REJECTED,
                "remarks": "Blurry scan; resubmit.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.version.refresh_from_db()
        self.assertEqual(
            self.version.verification_status,
            DocumentVersion.VerificationStatus.REJECTED,
        )

    def test_verification_events_are_listed(self):
        self.client.force_authenticate(self.hr_user)
        self.client.post(
            self.verify_url,
            {
                "decision": DocumentVerification.Decision.REJECTED,
                "remarks": "First pass rejected.",
            },
            format="json",
        )

        response = self.client.get(
            reverse("document-version-verifications", args=[self.version.id])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
