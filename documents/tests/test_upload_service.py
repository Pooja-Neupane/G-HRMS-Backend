import hashlib
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from documents.exceptions import (
    DocumentConflictError,
    DocumentUploadNotAllowedError,
    DocumentValidationError,
)
from documents.models import (
    DocumentCategory,
    DocumentVersion,
    EmployeeDocument,
)
from documents.services import DocumentUploadService
from employees.models import Employee


User = get_user_model()


class DocumentUploadServiceTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory.name
        )
        self.settings_override.enable()

        self.actor = User.objects.create_user(
            username="document-uploader",
            email="document-uploader@example.com",
            password="StrongPassword@123",
            role=User.Role.HR_PERSONNEL,
            status=User.Status.ACTIVE,
        )
        self.employee = Employee.objects.create(
            first_name="Document",
            last_name="Owner",
            ka_sa_num="EMP-UPLOAD-001",
            dob_bs="2050-01-01",
            dob_ad=date(1993, 4, 14),
            jobstartdate_bs="2080-01-01",
            jobstartdate_ad=date(2023, 4, 14),
            current_position_date_bs="2080-01-01",
            current_position_date_ad=date(2023, 4, 14),
            email="upload-owner@example.com",
        )
        self.category = DocumentCategory.objects.create(
            code="DOC-UPLOAD",
            name="Upload Test",
            allowed_extensions=["pdf"],
            max_file_size_mb=2,
        )
        self.document = EmployeeDocument.objects.create(
            code="EMP-DOC-UPLOAD",
            employee=self.employee,
            category=self.category,
            title="Upload Test",
        )
        self.service = DocumentUploadService()

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()

    def upload(self, *, name="document.pdf", content=b"document-content"):
        uploaded_file = SimpleUploadedFile(
            name,
            content,
            content_type="application/pdf",
        )
        return self.service.upload_new_version(
            document_id=self.document.id,
            uploaded_file=uploaded_file,
            upload_source=DocumentVersion.UploadSource.HR,
            actor=self.actor,
        )

    def test_first_upload_creates_current_version_with_trusted_metadata(self):
        content = b"trusted-content"

        version = self.upload(content=content)

        self.assertEqual(version.version_number, 1)
        self.assertTrue(version.is_current)
        self.assertEqual(version.file_size_bytes, len(content))
        self.assertEqual(
            version.file_hash_sha256,
            hashlib.sha256(content).hexdigest(),
        )
        self.assertEqual(version.original_file_name, "document.pdf")
        self.assertEqual(version.uploaded_by, self.actor)
        self.assertEqual(version.created_by, self.actor)
        self.assertEqual(
            version.verification_status,
            DocumentVersion.VerificationStatus.PENDING,
        )

    def test_second_upload_replaces_current_version(self):
        first = self.upload(content=b"first")
        second = self.upload(content=b"second")

        first.refresh_from_db()

        self.assertFalse(first.is_current)
        self.assertTrue(second.is_current)
        self.assertEqual(second.version_number, 2)
        self.assertEqual(
            DocumentVersion.objects.filter(
                document=self.document,
                is_current=True,
            ).count(),
            1,
        )

    def test_invalid_extension_is_rejected(self):
        with self.assertRaises(DocumentValidationError):
            self.upload(name="document.exe")

        self.assertFalse(
            DocumentVersion.objects.filter(document=self.document).exists()
        )

    def test_employee_upload_respects_category_policy(self):
        self.category.employee_can_upload = False
        self.category.save(update_fields=["employee_can_upload", "row_version"])

        uploaded_file = SimpleUploadedFile(
            "document.pdf",
            b"content",
            content_type="application/pdf",
        )

        with self.assertRaises(DocumentUploadNotAllowedError):
            self.service.upload_new_version(
                document_id=self.document.id,
                uploaded_file=uploaded_file,
                upload_source=DocumentVersion.UploadSource.EMPLOYEE,
                actor=self.actor,
            )

    def test_archived_document_rejects_new_version(self):
        self.document.lifecycle_status = (
            EmployeeDocument.LifecycleStatus.ARCHIVED
        )
        self.document.save(
            update_fields=["lifecycle_status", "row_version"]
        )

        with self.assertRaises(DocumentConflictError):
            self.upload()