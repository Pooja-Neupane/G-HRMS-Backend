from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from documents.models import (
    DocumentCategory,
    DocumentVerification,
    DocumentVersion,
    EmployeeDocument,
)
from employees.models import Employee


User = get_user_model()


class DocumentModelTests(TestCase):
    def setUp(self):
        self.reviewer = User.objects.create_user(
            username="document-reviewer",
            email="document-reviewer@example.com",
            password="StrongPassword@123",
            role=User.Role.HR_PERSONNEL,
            status=User.Status.ACTIVE,
        )
        self.employee = Employee.objects.create(
            first_name="Document",
            last_name="Owner",
            ka_sa_num="EMP-DOC-001",
            dob_bs="2050-01-01",
            dob_ad=date(1993, 4, 14),
            jobstartdate_bs="2080-01-01",
            jobstartdate_ad=date(2023, 4, 14),
            current_position_date_bs="2080-01-01",
            current_position_date_ad=date(2023, 4, 14),
            email="document-owner@example.com",
        )
        self.category = DocumentCategory.objects.create(
            code="DOC-CITIZENSHIP",
            name="Citizenship Certificate",
            allowed_extensions=["pdf", "jpg"],
            max_file_size_mb=2,
        )
        self.document = EmployeeDocument.objects.create(
            code="EMP-DOC-CIT-001",
            employee=self.employee,
            category=self.category,
            title="Citizenship Certificate",
        )
        self.version = self.create_version()

    def create_version(self, **overrides):
        values = {
            "document": self.document,
            "version_number": 1,
            "file": "employee-documents/test/citizenship.pdf",
            "original_file_name": "citizenship.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 1024,
            "file_hash_sha256": "a" * 64,
            "upload_source": DocumentVersion.UploadSource.HR,
            "uploaded_by": self.reviewer,
            "scan_status": DocumentVersion.ScanStatus.CLEAN,
        }
        values.update(overrides)
        return DocumentVersion.objects.create(**values)

    def test_employee_document_rejects_organization_category(self):
        category = DocumentCategory.objects.create(
            code="DOC-ORG-CIRCULAR",
            name="Organization Circular",
            scope=DocumentCategory.Scope.ORGANIZATION,
        )
        document = EmployeeDocument(
            code="EMP-DOC-INVALID",
            employee=self.employee,
            category=category,
            title="Invalid employee document",
        )

        with self.assertRaises(ValidationError) as context:
            document.full_clean()

        self.assertIn("category", context.exception.message_dict)

    def test_employee_document_rejects_expiry_before_issue(self):
        self.document.issue_date_ad = date(2025, 1, 2)
        self.document.expiry_date_ad = date(2025, 1, 1)

        with self.assertRaises(ValidationError) as context:
            self.document.full_clean()

        self.assertIn("expiry_date_ad", context.exception.message_dict)

    def test_version_rejects_disallowed_extension_and_oversized_file(self):
        version = DocumentVersion(
            document=self.document,
            version_number=2,
            file="employee-documents/test/citizenship.exe",
            original_file_name="citizenship.exe",
            content_type="application/octet-stream",
            file_size_bytes=3 * 1024 * 1024,
            file_hash_sha256="b" * 64,
            upload_source=DocumentVersion.UploadSource.HR,
            uploaded_by=self.reviewer,
            is_current=False,
        )

        with self.assertRaises(ValidationError) as context:
            version.full_clean()

        self.assertIn("file", context.exception.message_dict)

    def test_uploaded_file_metadata_cannot_be_changed(self):
        self.version.original_file_name = "replacement.pdf"

        with self.assertRaises(ValidationError) as context:
            self.version.full_clean()

        self.assertIn("original_file_name", context.exception.message_dict)

    def test_only_one_active_current_version_is_allowed(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.create_version(
                    version_number=2,
                    file_hash_sha256="b" * 64,
                )

    def test_verified_decision_requires_clean_scan(self):
        self.version.scan_status = DocumentVersion.ScanStatus.PENDING
        self.version.save(update_fields=["scan_status", "row_version"])
        verification = DocumentVerification(
            version=self.version,
            decision=DocumentVerification.Decision.VERIFIED,
            reviewed_by=self.reviewer,
            file_hash_sha256=self.version.file_hash_sha256,
        )

        with self.assertRaises(ValidationError) as context:
            verification.full_clean()

        self.assertIn("decision", context.exception.message_dict)

    def test_rejection_requires_remarks(self):
        verification = DocumentVerification(
            version=self.version,
            decision=DocumentVerification.Decision.REJECTED,
            reviewed_by=self.reviewer,
            file_hash_sha256=self.version.file_hash_sha256,
        )

        with self.assertRaises(ValidationError) as context:
            verification.full_clean()

        self.assertIn("remarks", context.exception.message_dict)

    def test_verification_is_bound_to_file_hash_and_append_only(self):
        verification = DocumentVerification(
            version=self.version,
            decision=DocumentVerification.Decision.VERIFIED,
            reviewed_by=self.reviewer,
            file_hash_sha256=self.version.file_hash_sha256,
        )
        verification.full_clean()
        verification.save()

        verification.remarks = "Changed after review"
        with self.assertRaises(PermissionError):
            verification.save()
        with self.assertRaises(PermissionError):
            verification.delete()

        mismatched = DocumentVerification(
            version=self.version,
            decision=DocumentVerification.Decision.VERIFIED,
            reviewed_by=self.reviewer,
            file_hash_sha256="c" * 64,
        )
        with self.assertRaises(ValidationError) as context:
            mismatched.full_clean()

        self.assertIn("file_hash_sha256", context.exception.message_dict)
