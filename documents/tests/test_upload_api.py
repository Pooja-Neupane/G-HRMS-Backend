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
    DocumentVersion,
    EmployeeDocument,
)
from employees.models import Employee


User = get_user_model()


class DocumentVersionUploadAPITests(APITestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory.name
        )
        self.settings_override.enable()

        self.hr_user = User.objects.create_user(
            username="hr-uploader",
            email="hr-uploader@example.com",
            password="StrongPassword@123",
            role=User.Role.HR_PERSONNEL,
            status=User.Status.ACTIVE,
        )
        self.employee = Employee.objects.create(
            first_name="Document",
            last_name="Owner",
            ka_sa_num="EMP-API-001",
            dob_bs="2050-01-01",
            dob_ad=date(1993, 4, 14),
            jobstartdate_bs="2080-01-01",
            jobstartdate_ad=date(2023, 4, 14),
            current_position_date_bs="2080-01-01",
            current_position_date_ad=date(2023, 4, 14),
            email="api-owner@example.com",
        )
        self.category = DocumentCategory.objects.create(
            code="DOC-API",
            name="API Test",
            allowed_extensions=["pdf"],
            max_file_size_mb=2,
        )
        self.document = EmployeeDocument.objects.create(
            code="EMP-DOC-API",
            employee=self.employee,
            category=self.category,
            title="API Test",
        )
        self.url = reverse("document-versions", args=[self.document.id])

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()

    def upload_payload(self, *, name="document.pdf", content=b"document-content",
                       upload_source=DocumentVersion.UploadSource.HR):
        return {
            "file": SimpleUploadedFile(
                name, content, content_type="application/pdf"
            ),
            "upload_source": upload_source,
        }

    def test_unauthenticated_upload_is_rejected(self):
        response = self.client.post(
            self.url, self.upload_payload(), format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(
            DocumentVersion.objects.filter(document=self.document).exists()
        )

    def test_hr_upload_creates_first_current_version(self):
        self.client.force_authenticate(self.hr_user)

        response = self.client.post(
            self.url, self.upload_payload(), format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["version_number"], 1)
        self.assertTrue(response.data["is_current"])
        self.assertEqual(response.data["original_file_name"], "document.pdf")
        self.assertEqual(
            response.data["verification_status"],
            DocumentVersion.VerificationStatus.PENDING,
        )

    def test_second_upload_replaces_current_version(self):
        self.client.force_authenticate(self.hr_user)

        self.client.post(
            self.url, self.upload_payload(content=b"first"), format="multipart"
        )
        response = self.client.post(
            self.url, self.upload_payload(content=b"second"), format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["version_number"], 2)
        self.assertEqual(
            DocumentVersion.objects.filter(
                document=self.document, is_current=True
            ).count(),
            1,
        )

    def test_invalid_extension_is_rejected(self):
        self.client.force_authenticate(self.hr_user)

        response = self.client.post(
            self.url,
            self.upload_payload(name="document.exe"),
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            DocumentVersion.objects.filter(document=self.document).exists()
        )

    def test_employee_upload_respects_category_policy(self):
        self.category.employee_can_upload = False
        self.category.save(update_fields=["employee_can_upload", "row_version"])
        self.client.force_authenticate(self.hr_user)

        response = self.client.post(
            self.url,
            self.upload_payload(
                upload_source=DocumentVersion.UploadSource.EMPLOYEE
            ),
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_versions_listing_returns_uploaded_versions(self):
        self.client.force_authenticate(self.hr_user)
        self.client.post(
            self.url, self.upload_payload(), format="multipart"
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertTrue(response.data[0]["is_current"])
