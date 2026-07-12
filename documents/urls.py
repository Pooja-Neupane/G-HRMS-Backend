from rest_framework.routers import DefaultRouter

from documents.views import DocumentVersionViewSet, EmployeeDocumentViewSet

router = DefaultRouter()
router.register(r"documents", EmployeeDocumentViewSet, basename="document")
router.register(
    r"document-versions", DocumentVersionViewSet, basename="document-version"
)
urlpatterns = router.urls
