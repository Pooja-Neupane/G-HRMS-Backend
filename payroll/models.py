from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from core.models import BaseModel
from employees.models import Employee
from organizations.models import Organization


class PayrollRun(BaseModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        PROCESSING = "PROCESSING", "Processing"
        CLOSED = "CLOSED", "Closed"

    run_code = models.CharField(max_length=40, unique=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="payroll_runs",
    )
    period_month = models.CharField(max_length=7)
    cutoff_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    remarks = models.TextField(blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-cutoff_date", "-created_at"]

    def __str__(self):
        return f"{self.run_code} ({self.organization.code})"


class PayrollEntry(BaseModel):
    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        PARTIAL = "PARTIAL", "Partial"
        FAILED = "FAILED", "Failed"

    payroll_run = models.ForeignKey(
        PayrollRun,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="payroll_entries",
    )
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    gross_pay = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    remarks = models.TextField(blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["payroll_run", "employee"],
                name="unique_payroll_entry_per_employee_per_run",
            )
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.payroll_run_id and self.employee_id:
            if self.payroll_run.organization_id != self.employee.working_organization_id:
                errors["employee"] = (
                    "The employee must belong to the payroll run organization."
                )
        if self.basic_salary < 0:
            errors["basic_salary"] = "Basic salary cannot be negative."
        if self.allowances < 0:
            errors["allowances"] = "Allowances cannot be negative."
        if self.deductions < 0:
            errors["deductions"] = "Deductions cannot be negative."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.gross_pay = self.basic_salary + self.allowances
        self.net_pay = self.gross_pay - self.deductions
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee} - {self.payroll_run.run_code}"


class PayrollPayment(BaseModel):
    class Method(models.TextChoices):
        BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer"
        CASH = "CASH", "Cash"
        MOBILE_WALLET = "MOBILE_WALLET", "Mobile Wallet"

    class Status(models.TextChoices):
        PAID = "PAID", "Paid"
        PENDING = "PENDING", "Pending"
        FAILED = "FAILED", "Failed"

    payroll_entry = models.ForeignKey(
        PayrollEntry,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payment_method = models.CharField(
        max_length=20,
        choices=Method.choices,
        default=Method.BANK_TRANSFER,
    )
    reference = models.CharField(max_length=80, blank=True)
    paid_on = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    remarks = models.TextField(blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-paid_on", "-created_at"]

    def clean(self):
        super().clean()
        errors = {}
        if self.amount < 0:
            errors["amount"] = "Payment amount cannot be negative."
        if self.amount and self.payroll_entry_id and self.amount > self.payroll_entry.net_pay:
            errors["amount"] = "Payment amount cannot exceed net pay."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        is_paid = self.status == self.Status.PAID
        if is_paid:
            self.paid_on = self.paid_on or timezone.now()
        result = super().save(*args, **kwargs)
        if is_paid:
            self.payroll_entry.payment_status = PayrollEntry.PaymentStatus.PAID
            self.payroll_entry.save(update_fields=["payment_status", "updated_at"])
        return result

    def __str__(self):
        return f"{self.payroll_entry} - {self.amount}"
