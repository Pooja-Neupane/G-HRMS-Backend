from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from account.models import User
from employees.models import AttendanceRecord, Employee, LeaveRequest


class ReportApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="reportuser",
            email="report@example.com",
            password="securepass123",
            role=User.Role.HR_PERSONNEL,
        )
        self.client.force_authenticate(self.user)

        self.employee = Employee.objects.create(
            ka_sa_num="EMP-2001",
            first_name="Nabin",
            middle_name="",
            last_name="Karki",
            dob_bs="2051-02-02",
            dob_ad="1994-05-15",
            jobstartdate_bs="2081-02-02",
            jobstartdate_ad="2024-05-15",
            current_position_date_bs="2081-02-02",
            current_position_date_ad="2024-05-15",
            email="nabin@example.com",
        )

        AttendanceRecord.objects.create(
            employee=self.employee,
            work_date="2026-07-21",
            status=AttendanceRecord.Status.PRESENT,
        )
        AttendanceRecord.objects.create(
            employee=self.employee,
            work_date="2026-07-22",
            status=AttendanceRecord.Status.ABSENT,
        )
        LeaveRequest.objects.create(
            employee=self.employee,
            leave_type=LeaveRequest.LeaveType.SICK,
            start_date="2026-07-23",
            end_date="2026-07-24",
            reason="Fever",
            status=LeaveRequest.Status.PENDING,
        )

    def test_report_endpoint_returns_summary(self):
        response = self.client.get(
            reverse("report-list"),
            {
                "employee": self.employee.id,
                "start_date": "2026-07-21",
                "end_date": "2026-07-24",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["employee_id"], self.employee.id)
        self.assertEqual(payload["attendance"]["total"], 2)
        self.assertEqual(payload["attendance"]["present"], 1)
        self.assertEqual(payload["attendance"]["absent"], 1)
        self.assertEqual(payload["leave_requests"]["total"], 1)
        self.assertEqual(payload["leave_requests"]["pending"], 1)
