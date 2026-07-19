from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets

from account.models import ModuleKey
from payroll.models import PayrollEntry, PayrollPayment, PayrollRun
from payroll.permissions import PayrollPermission
from payroll.serializers import PayrollEntrySerializer, PayrollPaymentSerializer, PayrollRunSerializer


@extend_schema(tags=["Payroll"])
class PayrollRunViewSet(viewsets.ModelViewSet):
    permission_classes = [PayrollPermission]
    module_key = ModuleKey.PAYROLL
    queryset = PayrollRun.objects.select_related("organization", "created_by")
    serializer_class = PayrollRunSerializer
    filterset_fields = ["organization", "status"]
    search_fields = ["run_code", "period_month", "remarks"]
    ordering_fields = ["id", "cutoff_date", "period_month"]
    ordering = ["-cutoff_date"]


@extend_schema(tags=["Payroll"])
class PayrollEntryViewSet(viewsets.ModelViewSet):
    permission_classes = [PayrollPermission]
    module_key = ModuleKey.PAYROLL
    queryset = PayrollEntry.objects.select_related(
        "payroll_run",
        "employee",
        "employee__working_organization",
    )
    serializer_class = PayrollEntrySerializer
    filterset_fields = ["payroll_run", "employee", "payment_status"]
    search_fields = ["employee__ka_sa_num", "employee__first_name", "remarks"]
    ordering_fields = ["id", "basic_salary", "gross_pay", "net_pay"]
    ordering = ["-id"]


@extend_schema(tags=["Payroll"])
class PayrollPaymentViewSet(viewsets.ModelViewSet):
    permission_classes = [PayrollPermission]
    module_key = ModuleKey.PAYROLL
    queryset = PayrollPayment.objects.select_related("payroll_entry", "payroll_entry__employee")
    serializer_class = PayrollPaymentSerializer
    filterset_fields = ["payroll_entry", "status", "payment_method"]
    search_fields = ["reference", "payroll_entry__employee__ka_sa_num"]
    ordering_fields = ["id", "amount", "paid_on"]
    ordering = ["-paid_on"]

    def perform_create(self, serializer):
        payment = serializer.save()
        if payment.status == PayrollPayment.Status.PAID:
            entry = payment.payroll_entry
            entry.payment_status = PayrollEntry.PaymentStatus.PAID
            entry.save(update_fields=["payment_status", "updated_at"])

    def perform_update(self, serializer):
        payment = serializer.save()
        if payment.status == PayrollPayment.Status.PAID:
            entry = payment.payroll_entry
            entry.payment_status = PayrollEntry.PaymentStatus.PAID
            entry.save(update_fields=["payment_status", "updated_at"])
