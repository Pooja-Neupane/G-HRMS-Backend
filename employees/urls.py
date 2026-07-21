from rest_framework.routers import DefaultRouter
from .views import (
    ApprovalViewSet,
    AttendanceRecordViewSet,
    EmployeeViewSet,
    LeaveRequestViewSet,
    OfficeTransferViewSet,
)

router = DefaultRouter()
router.register(r"employees", EmployeeViewSet, basename="employee")
router.register(r"attendance-records", AttendanceRecordViewSet, basename="attendance-record")
router.register(r"leave-requests", LeaveRequestViewSet, basename="leave-request")
router.register(r"approvals", ApprovalViewSet, basename="approval")
router.register(r"office-transfers", OfficeTransferViewSet)
urlpatterns = router.urls
