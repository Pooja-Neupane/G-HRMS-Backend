from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from employees.models import (
    Employee,
    EmployeeContact,
    EmployeeStatusHistory,
    OfficeTransfer,
    ServiceBookEntry,
)
from employees.serializers import EmployeeWriteSerializer
from employees.services import EmployeeService
from organizations.models import Level, Organization, OrganizationPosition, Position


User = get_user_model()


class EmployeeDomainModelTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Ministry",
            code="ORG-EMP",
            org_type=Organization.UnitType.MINISTRY,
            province="03",
        )
        self.level = Level.objects.create(name="Level 7")
        self.other_level = Level.objects.create(name="Level 8")
        self.position = Position.objects.create(
            title="HR Officer",
            level=self.level,
        )
        self.other_position = Position.objects.create(title="Finance Officer")
        self.employee = self.create_employee()

    def create_employee(self, **overrides):
        sequence = Employee.all_objects.count() + 1
        values = {
            "first_name": "Test",
            "last_name": "Employee",
            "ka_sa_num": f"EMP-{sequence:03d}",
            "dob_bs": "2050-01-01",
            "dob_ad": date(1993, 4, 14),
            "jobstartdate_bs": "2080-01-01",
            "jobstartdate_ad": date(2023, 4, 14),
            "current_position_date_bs": "2080-01-01",
            "current_position_date_ad": date(2023, 4, 14),
            "email": f"employee{sequence}@example.com",
            "working_organization": self.organization,
            "position": self.position,
            "level": self.level,
        }
        values.update(overrides)
        return Employee.objects.create(**values)

    def test_status_change_writes_old_and_new_status(self):
        self.employee.status = Employee.Status.SUSPENDED
        self.employee.save(update_fields=["status"])

        history = EmployeeStatusHistory.objects.get(employee=self.employee)
        self.assertEqual(history.old_status, Employee.Status.IN_SERVICE)
        self.assertEqual(history.new_status, Employee.Status.SUSPENDED)

    def test_serializer_rejects_level_that_conflicts_with_position(self):
        serializer = EmployeeWriteSerializer(
            self.employee,
            data={"level": self.other_level.pk},
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("level", serializer.errors)

    def test_serializer_enforces_sanctioned_positions_when_configured(self):
        OrganizationPosition.objects.create(
            organization=self.organization,
            position=self.position,
            sanctioned_count=1,
        )
        serializer = EmployeeWriteSerializer(
            self.employee,
            data={"position": self.other_position.pk},
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("position", serializer.errors)

    def test_supervisor_cycle_is_invalid(self):
        manager = self.create_employee(
            first_name="Manager",
            ka_sa_num="EMP-MANAGER",
            email="manager@example.com",
            supervisor=self.employee,
        )
        self.employee.supervisor = manager

        with self.assertRaises(ValidationError):
            self.employee.full_clean()

    def test_employee_soft_delete_preserves_record(self):
        employee_id = self.employee.pk

        self.employee.delete()

        self.assertFalse(Employee.objects.filter(pk=employee_id).exists())
        self.assertTrue(Employee.all_objects.filter(pk=employee_id).exists())

    def test_service_book_entry_is_append_only(self):
        entry = ServiceBookEntry.objects.create(
            employee=self.employee,
            entry_type=ServiceBookEntry.EntryType.APPOINTMENT,
            effective_date=date(2023, 4, 14),
        )

        entry.remarks = "Changed"
        with self.assertRaises(PermissionError):
            entry.save()
        with self.assertRaises(PermissionError):
            entry.delete()

    def test_contact_soft_delete_preserves_history(self):
        contact = EmployeeContact.objects.create(
            employee=self.employee,
            kind=EmployeeContact.Kind.PHONE,
            value="9800000000",
            is_primary=True,
        )

        contact.delete()

        self.assertFalse(EmployeeContact.objects.filter(pk=contact.pk).exists())
        self.assertTrue(EmployeeContact.all_objects.filter(pk=contact.pk).exists())


class EmployeeServiceTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(
            username="hr-service",
            email="hr-service@example.com",
            password="StrongPassword@123",
            role=User.Role.HR_PERSONNEL,
            status=User.Status.ACTIVE,
        )
        self.organization = Organization.objects.create(
            name="Service Ministry",
            code="EMP-SVC-ORG",
            org_type=Organization.UnitType.MINISTRY,
            province="03",
        )
        self.new_organization = Organization.objects.create(
            name="Service Department",
            code="EMP-SVC-DEPT",
            org_type=Organization.UnitType.DEPARTMENT,
            province="03",
            parent_org=self.organization,
        )
        self.service = EmployeeService()

    def employee_data(self):
        return {
            "first_name": "Sita",
            "last_name": "Shrestha",
            "ka_sa_num": "EMP-SERVICE-001",
            "dob_bs": "2050-01-01",
            "dob_ad": date(1993, 4, 14),
            "jobstartdate_bs": "2080-01-01",
            "jobstartdate_ad": date(2023, 4, 14),
            "current_position_date_bs": "2080-01-01",
            "current_position_date_ad": date(2023, 4, 14),
            "email": "sita.service@example.com",
            "working_organization": self.organization,
        }

    def test_create_is_audited_and_creates_one_recruitment_record(self):
        employee = self.service.create(data=self.employee_data(), actor=self.actor)

        self.assertEqual(employee.created_by, self.actor)
        self.assertEqual(employee.initiated_by, self.actor)
        transfers = OfficeTransfer.objects.filter(employee=employee)
        self.assertEqual(transfers.count(), 1)
        self.assertEqual(transfers.get().status, OfficeTransfer.Status.RECRUITED)
        self.assertEqual(transfers.get().initiated_by, self.actor)

    def test_update_records_transfer_and_status_change_once(self):
        employee = self.service.create(data=self.employee_data(), actor=self.actor)

        self.service.update(
            employee_id=employee.pk,
            data={
                "working_organization": self.new_organization,
                "status": Employee.Status.IN_LEAVE,
            },
            actor=self.actor,
        )

        self.assertEqual(
            OfficeTransfer.objects.filter(
                employee=employee,
                status=OfficeTransfer.Status.TRANSFERRED,
            ).count(),
            1,
        )
        history = EmployeeStatusHistory.objects.get(employee=employee)
        self.assertEqual(history.old_status, Employee.Status.IN_SERVICE)
        self.assertEqual(history.new_status, Employee.Status.IN_LEAVE)


class EmployeeApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.hr_user = User.objects.create_user(
            username="employee-hr",
            email="employee-hr@example.com",
            password="StrongPassword@123",
            role=User.Role.HR_PERSONNEL,
            status=User.Status.ACTIVE,
        )
        self.viewer = User.objects.create_user(
            username="employee-viewer",
            email="employee-viewer@example.com",
            password="StrongPassword@123",
            role=User.Role.VIEWER,
            status=User.Status.ACTIVE,
        )
        self.organization = Organization.objects.create(
            name="Employee Ministry",
            code="EMP-API-ORG",
            org_type=Organization.UnitType.MINISTRY,
            province="03",
        )
        self.level = Level.objects.create(name="Seventh Level")
        self.position = Position.objects.create(
            title="Personnel Officer",
            level=self.level,
        )

    def payload(self, **overrides):
        data = {
            "ka_sa_num": "EMP-API-001",
            "first_name": "Sita",
            "middle_name": "Kumari",
            "last_name": "Shrestha",
            "father_name": "Ram Shrestha",
            "grandfather_name": "Hari Shrestha",
            "spouse_name": "",
            "beneficiary_name": "Aarav Shrestha",
            "permanent_address": "Hetauda, Makwanpur",
            "citizenship_number": "31-01-75-12345",
            "gender": "Female",
            "dob_bs": "2050-01-01",
            "dob_ad": "1993-04-14",
            "email": "sita.api@example.com",
            "phone_number": "+9779812345678",
            "employment_type": Employee.EmploymentType.PERMANENT,
            "status": Employee.Status.IN_SERVICE,
            "jobstartdate_bs": "2080-01-01",
            "jobstartdate_ad": "2023-04-14",
            "current_position_date_bs": "2080-01-01",
            "current_position_date_ad": "2023-04-14",
            "working_organization": self.organization.pk,
            "position": self.position.pk,
            "level": self.level.pk,
            "supervisor": None,
            "remarks": "Initial appointment",
        }
        data.update(overrides)
        return data

    def test_employee_access_policy(self):
        self.assertEqual(self.client.get(reverse("employee-list")).status_code, 401)

        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(reverse("employee-list")).status_code, 200)
        self.assertEqual(
            self.client.post(
                reverse("employee-list"), self.payload(), format="json"
            ).status_code,
            403,
        )

    def test_hr_can_create_read_update_and_soft_delete_employee(self):
        self.client.force_authenticate(self.hr_user)
        created = self.client.post(
            reverse("employee-list"),
            self.payload(),
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        employee_id = created.data["id"]
        self.assertEqual(created.data["full_name"], "Sita Kumari Shrestha")
        self.assertEqual(
            created.data["working_organization"]["code"], "EMP-API-ORG"
        )
        self.assertEqual(created.data["position"]["title"], "Personnel Officer")
        self.assertNotIn("is_deleted", created.data)
        self.assertNotIn("deleted_by", created.data)

        updated = self.client.patch(
            reverse("employee-detail", kwargs={"pk": employee_id}),
            {"status": Employee.Status.IN_LEAVE},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["status"], Employee.Status.IN_LEAVE)
        self.assertTrue(
            EmployeeStatusHistory.objects.filter(
                employee_id=employee_id,
                new_status=Employee.Status.IN_LEAVE,
            ).exists()
        )

        deleted = self.client.delete(
            reverse("employee-detail", kwargs={"pk": employee_id})
        )
        self.assertEqual(deleted.status_code, 204)
        employee = Employee.all_objects.get(pk=employee_id)
        self.assertTrue(employee.is_deleted)
        self.assertEqual(employee.deleted_by, self.hr_user)

    def test_create_rejects_invalid_dates_and_position_level(self):
        self.client.force_authenticate(self.hr_user)
        wrong_level = Level.objects.create(name="Eighth Level")

        response = self.client.post(
            reverse("employee-list"),
            self.payload(
                jobstartdate_ad="1990-01-01",
                level=wrong_level.pk,
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("jobstartdate_ad", response.data["error"]["details"])
        self.assertIn("level", response.data["error"]["details"])

    def test_create_requires_complete_personnel_profile(self):
        self.client.force_authenticate(self.hr_user)
        payload = self.payload()
        for field in (
            "father_name",
            "grandfather_name",
            "beneficiary_name",
            "permanent_address",
            "citizenship_number",
            "gender",
            "phone_number",
            "position",
            "level",
        ):
            payload.pop(field)

        response = self.client.post(
            reverse("employee-list"), payload, format="json"
        )

        self.assertEqual(response.status_code, 400)
        for field in (
            "father_name",
            "grandfather_name",
            "beneficiary_name",
            "permanent_address",
            "citizenship_number",
            "gender",
            "phone_number",
            "position",
            "level",
        ):
            self.assertIn(field, response.data["error"]["details"])

    def test_office_transfer_endpoint_protects_internal_verification_fields(self):
        self.client.force_authenticate(self.hr_user)
        employee = EmployeeService().create(
            data={
                **self.payload(),
                "working_organization": self.organization,
                "position": self.position,
                "level": self.level,
                "dob_ad": date(1993, 4, 14),
                "jobstartdate_ad": date(2023, 4, 14),
                "current_position_date_ad": date(2023, 4, 14),
            },
            actor=self.hr_user,
        )
        response = self.client.post(
            reverse("officetransfer-list"),
            {
                "employee": employee.pk,
                "to_organization": self.organization.pk,
                "status": OfficeTransfer.Status.KAAJ,
                "verified": True,
                "verified_by": self.viewer.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        transfer = OfficeTransfer.objects.get(pk=response.data["id"])
        self.assertEqual(transfer.initiated_by, self.hr_user)
        self.assertFalse(transfer.verified)
        self.assertIsNone(transfer.verified_by)


class EmployeeOpenApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.schema = SchemaGenerator().get_schema(request=None, public=True)

    def test_employee_request_excludes_internal_fields_and_has_choices(self):
        request_schema = self.schema["components"]["schemas"][
            "EmployeeCreateRequest"
        ]
        properties = request_schema["properties"]
        for internal_field in (
            "initiated_by",
            "created_by",
            "updated_by",
            "is_deleted",
            "deleted_by",
            "row_version",
        ):
            self.assertNotIn(internal_field, properties)

        self.assertIn("working_organization", request_schema["required"])
        for required_profile_field in (
            "father_name",
            "grandfather_name",
            "beneficiary_name",
            "permanent_address",
            "citizenship_number",
            "gender",
            "phone_number",
            "position",
            "level",
        ):
            self.assertIn(required_profile_field, request_schema["required"])
        self.assertNotIn("spouse_name", request_schema["required"])
        self.assertEqual(
            self.schema["components"]["schemas"]["EmployeeStatusEnum"]["enum"],
            [
                "IN_SERVICE",
                "SUSPENDED",
                "IN_LEAVE",
                "RETIRED",
                "TERMINATED",
                "DECEASED",
            ],
        )

    def test_employee_create_has_documented_example(self):
        examples = self.schema["paths"]["/api/employees/"]["post"][
            "requestBody"
        ]["content"]["application/json"]["examples"]
        self.assertIn("CreateAnEmployee", examples)
