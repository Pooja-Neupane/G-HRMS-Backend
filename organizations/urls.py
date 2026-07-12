from rest_framework.routers import DefaultRouter
from .views import (
    OrganizationViewSet,
    ServiceViewSet,
    CategoryViewSet,
    SubCategoryViewSet,
    PositionViewSet,
    LevelViewSet,
)

router = DefaultRouter()
router.register(r"organizations", OrganizationViewSet, basename="organization")
router.register(r"services", ServiceViewSet, basename="service")
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"subcategories", SubCategoryViewSet, basename="subcategory")
router.register(r"positions", PositionViewSet, basename="position")
router.register(r"levels", LevelViewSet, basename="level")

urlpatterns = router.urls
