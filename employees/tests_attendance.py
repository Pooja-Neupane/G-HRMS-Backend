from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from account.models import User
from employees.models import AttendanceRecord, Employee, LeaveRequest


class AttendanceLeaveApprovalApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="hruser",
            email="hr@example.com",
            password="securepass123",
            role=User.Role.HR_PERSONNEL,
        )
        self.client.force_authenticate(self.user)

        self.employee = Employee.objects.create(
            ka_sa_num="EMP-1001",
            first_name="Sita",
            middle_name="",
            last_name="Sharma",
            dob_bs="2050-01-01",
            dob_ad="1993-04-14",
            jobstartdate_bs="2080-01-01",
            jobstartdate_ad="2023-04-14",
            current_position_date_bs="2080-01-01",
            current_position_date_ad="2023-04-14",
            email="sita@example.com",
        )

    def test_attendance_and_leave_approval_flow(self):
        attendance_response = self.client.post(
            reverse("attendance-record-list"),
            {
                "employee": self.employee.id,
                "work_date": "2026-07-21",
                "check_in": "09:00:00",
                "check_out": "17:00:00",
                "status": "present",
                "notes": "On time",
            },
            format="json",
        )
        self.assertEqual(attendance_response.status_code, 201)
        self.assertEqual(attendance_response.json()["status"], "present")
        self.assertEqual(attendance_response.json()["attendance_mark"], "on_time")

        late_record = AttendanceRecord.objects.create(
            employee=self.employee,
            work_date="2026-07-22",
            check_in="10:10:00",
            check_out="17:00:00",
            status=AttendanceRecord.Status.PRESENT,
        )
        self.assertEqual(late_record.attendance_mark, AttendanceRecord.AttendanceMark.LATE)

        leave_response = self.client.post(
            reverse("leave-request-list"),
            {
                "employee": self.employee.id,
                "leave_type": "sick",
                "start_date": "2026-07-22",
                "end_date": "2026-07-23",
                "reason": "Fever",
            },
            format="json",
        )
        self.assertEqual(leave_response.status_code, 201)
        self.assertEqual(leave_response.json()["status"], "pending")

        leave_request = LeaveRequest.objects.get(pk=leave_response.json()["id"])
        approve_response = self.client.post(
            reverse("leave-request-approve", kwargs={"pk": leave_request.pk}),
            {"remarks": "Approved by HR"},
            format="json",
        )
        self.assertEqual(approve_response.status_code, 200)
        leave_request.refresh_from_db()
        self.assertEqual(leave_request.status, LeaveRequest.Status.APPROVED)

        pending_response = self.client.get(reverse("approval-list"))
        self.assertEqual(pending_response.status_code, 200)
        self.assertEqual(pending_response.json()["count"], 0)
