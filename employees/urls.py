from rest_framework.routers import DefaultRouter
from .views import EmployeeViewSet, OfficeTransferViewSet

router = DefaultRouter()
router.register(r"employees", EmployeeViewSet, basename="employee")
router.register(r"office-transfers", OfficeTransferViewSet)
urlpatterns = router.urls
