from django.contrib import admin

from payroll.models import PayrollEntry, PayrollPayment, PayrollRun


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ("run_code", "organization", "period_month", "status", "cutoff_date")


@admin.register(PayrollEntry)
class PayrollEntryAdmin(admin.ModelAdmin):
    list_display = (
        "payroll_run",
        "employee",
        "basic_salary",
        "gross_pay",
        "net_pay",
        "payment_status",
    )


@admin.register(PayrollPayment)
class PayrollPaymentAdmin(admin.ModelAdmin):
    list_display = ("payroll_entry", "amount", "payment_method", "status", "paid_on")
