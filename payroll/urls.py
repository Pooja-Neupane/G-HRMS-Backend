from rest_framework.routers import DefaultRouter

from payroll.views import PayrollEntryViewSet, PayrollPaymentViewSet, PayrollRunViewSet

router = DefaultRouter()
router.register(r"payroll-runs", PayrollRunViewSet, basename="payrollrun")
router.register(r"payroll-entries", PayrollEntryViewSet, basename="payrollentry")
router.register(r"payroll-payments", PayrollPaymentViewSet, basename="payrollpayment")

urlpatterns = router.urls
