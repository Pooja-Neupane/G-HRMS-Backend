from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from employees.models import Employee
from employees.services import EmployeeService
from organizations.models import Level, Organization, Position
from payroll.models import PayrollEntry, PayrollPayment, PayrollRun

User = get_user_model()


class PayrollApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.hr_user = User.objects.create_user(
            username="payroll-hr",
            email="payroll-hr@example.com",
            password="StrongPassword@123",
            role=User.Role.HR_PERSONNEL,
            status=User.Status.ACTIVE,
        )
        self.organization = Organization.objects.create(
            name="Payroll Ministry",
            code="PAY-ORG",
            org_type=Organization.UnitType.MINISTRY,
            province="03",
        )
        self.level = Level.objects.create(name="Level 6")
        self.position = Position.objects.create(title="Senior Clerk", level=self.level)
        self.employee = EmployeeService().create(
            data={
                "first_name": "Payroll",
                "last_name": "Employee",
                "ka_sa_num": "EMP-PAY-001",
                "dob_bs": "2050-01-01",
                "dob_ad": date(1993, 4, 14),
                "jobstartdate_bs": "2080-01-01",
                "jobstartdate_ad": date(2023, 4, 14),
                "current_position_date_bs": "2080-01-01",
                "current_position_date_ad": date(2023, 4, 14),
                "email": "payroll.employee@example.com",
                "working_organization": self.organization,
                "position": self.position,
                "level": self.level,
            },
            actor=self.hr_user,
        )

    def test_payroll_run_and_payment_flow_creates_audited_records(self):
        self.client.force_authenticate(self.hr_user)

        run_response = self.client.post(
            reverse("payrollrun-list"),
            {
                "run_code": "PAY-2026-07",
                "organization": self.organization.pk,
                "period_month": "2026-07",
                "cutoff_date": "2026-07-31",
                "status": PayrollRun.Status.OPEN,
            },
            format="json",
        )
        self.assertEqual(run_response.status_code, 201, run_response.data)

        entry_response = self.client.post(
            reverse("payrollentry-list"),
            {
                "payroll_run": run_response.data["id"],
                "employee": self.employee.pk,
                "basic_salary": "75000.00",
                "allowances": "5000.00",
                "deductions": "2000.00",
                "payment_status": PayrollEntry.PaymentStatus.PENDING,
            },
            format="json",
        )
        self.assertEqual(entry_response.status_code, 201, entry_response.data)
        entry = PayrollEntry.objects.get(pk=entry_response.data["id"])
        self.assertEqual(entry.gross_pay, Decimal("80000.00"))
        self.assertEqual(entry.net_pay, Decimal("78000.00"))

        payment_response = self.client.post(
            reverse("payrollpayment-list"),
            {
                "payroll_entry": entry.pk,
                "amount": "78000.00",
                "payment_method": PayrollPayment.Method.BANK_TRANSFER,
                "reference": "TRX-001",
                "status": PayrollPayment.Status.PAID,
            },
            format="json",
        )
        self.assertEqual(payment_response.status_code, 201, payment_response.data)

        payment = PayrollPayment.objects.get(pk=payment_response.data["id"])
        self.assertEqual(payment.amount, Decimal("78000.00"))
        self.assertEqual(payment.status, PayrollPayment.Status.PAID)
        entry.refresh_from_db()
        self.assertEqual(entry.payment_status, PayrollEntry.PaymentStatus.PAID)
