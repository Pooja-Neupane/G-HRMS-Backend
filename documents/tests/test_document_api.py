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


class EmployeeDocumentAPITests(APITestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory.name
        )
        self.settings_override.enable()

        self.hr_user = User.objects.create_user(
            username="hr-doc",
            email="hr-doc@example.com",
            password="StrongPassword@123",
            role=User.Role.HR_PERSONNEL,
            status=User.Status.ACTIVE,
        )
        self.viewer = User.objects.create_user(
            username="viewer",
            email="viewer@example.com",
            password="StrongPassword@123",
            role=User.Role.VIEWER,
            status=User.Status.ACTIVE,
        )
        self.employee = Employee.objects.create(
            first_name="Document",
            last_name="Owner",
            ka_sa_num="EMP-DOC-CRUD-001",
            dob_bs="2050-01-01",
            dob_ad=date(1993, 4, 14),
            jobstartdate_bs="2080-01-01",
            jobstartdate_ad=date(2023, 4, 14),
            current_position_date_bs="2080-01-01",
            current_position_date_ad=date(2023, 4, 14),
            email="crud-owner@example.com",
        )
        self.category = DocumentCategory.objects.create(
            code="DOC-CRUD",
            name="CRUD Test",
            allowed_extensions=["pdf"],
            max_file_size_mb=2,
        )
        self.list_url = reverse("document-list")

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()

    def submit_payload(self, *, category=None, name="document.pdf",
                       content=b"document-content", **overrides):
        data = {
            "employee": self.employee.id,
            "category": (category or self.category).id,
            "title": "Citizenship Certificate",
            "document_number": "31-01-75-12345",
            "file": SimpleUploadedFile(
                name, content, content_type="application/pdf"
            ),
        }
        data.update(overrides)
        return data

    def test_hr_submit_creates_document_with_first_version(self):
        self.client.force_authenticate(self.hr_user)

        response = self.client.post(
            self.list_url, self.submit_payload(), format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["code"].startswith("DOC-"))
        self.assertEqual(response.data["employee"]["id"], self.employee.id)
        self.assertIsNotNone(response.data["current_version"])
        self.assertEqual(response.data["current_version"]["version_number"], 1)
        self.assertEqual(
            response.data["current_version"]["upload_source"],
            DocumentVersion.UploadSource.HR,
        )

    def test_non_privileged_user_cannot_submit(self):
        self.client.force_authenticate(self.viewer)

        response = self.client.post(
            self.list_url, self.submit_payload(), format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_resubmit_single_instance_appends_version(self):
        self.client.force_authenticate(self.hr_user)

        first = self.client.post(
            self.list_url,
            self.submit_payload(content=b"first"),
            format="multipart",
        )
        second = self.client.post(
            self.list_url,
            self.submit_payload(content=b"second", title="Updated Title"),
            format="multipart",
        )

        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        # Same logical document, new version, refreshed metadata.
        self.assertEqual(second.data["id"], first.data["id"])
        self.assertEqual(second.data["current_version"]["version_number"], 2)
        self.assertEqual(second.data["title"], "Updated Title")
        self.assertEqual(
            EmployeeDocument.objects.filter(
                employee=self.employee, category=self.category
            ).count(),
            1,
        )
        self.assertEqual(
            DocumentVersion.objects.filter(
                document_id=first.data["id"]
            ).count(),
            2,
        )

    def test_multi_instance_category_creates_separate_documents(self):
        multi_category = DocumentCategory.objects.create(
            code="DOC-MULTI",
            name="Multi Test",
            allowed_extensions=["pdf"],
            max_file_size_mb=2,
            allow_multiple=True,
        )
        self.client.force_authenticate(self.hr_user)

        first = self.client.post(
            self.list_url,
            self.submit_payload(category=multi_category),
            format="multipart",
        )
        second = self.client.post(
            self.list_url,
            self.submit_payload(category=multi_category),
            format="multipart",
        )

        self.assertNotEqual(first.data["id"], second.data["id"])
        self.assertEqual(
            EmployeeDocument.objects.filter(
                employee=self.employee, category=multi_category
            ).count(),
            2,
        )

    def test_authenticated_user_can_list_and_retrieve(self):
        document = EmployeeDocument.objects.create(
            code="EMP-DOC-READ",
            employee=self.employee,
            category=self.category,
            title="Read Test",
        )
        self.client.force_authenticate(self.viewer)

        list_response = self.client.get(self.list_url)
        detail_response = self.client.get(
            reverse("document-detail", args=[document.id])
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["title"], "Read Test")

    def test_partial_update_changes_title(self):
        document = EmployeeDocument.objects.create(
            code="EMP-DOC-PATCH",
            employee=self.employee,
            category=self.category,
            title="Before",
        )
        self.client.force_authenticate(self.hr_user)

        response = self.client.patch(
            reverse("document-detail", args=[document.id]),
            {"title": "After"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        document.refresh_from_db()
        self.assertEqual(document.title, "After")

    def test_destroy_soft_deletes(self):
        document = EmployeeDocument.objects.create(
            code="EMP-DOC-DEL",
            employee=self.employee,
            category=self.category,
            title="Delete Me",
        )
        self.client.force_authenticate(self.hr_user)

        response = self.client.delete(
            reverse("document-detail", args=[document.id])
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            EmployeeDocument.objects.filter(pk=document.id).exists()
        )
        self.assertTrue(
            EmployeeDocument.all_objects.filter(
                pk=document.id, is_deleted=True
            ).exists()
        )
