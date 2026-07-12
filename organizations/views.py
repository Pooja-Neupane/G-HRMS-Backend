"""Thin HTTP adapters for organization and classification CRUD."""

from drf_spectacular.utils import (
    OpenApiExample,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status, viewsets
from rest_framework.response import Response

from organizations.permissions import OrganizationCatalogPermission
from organizations.serializers import (
    CategorySerializer,
    LevelSerializer,
    OrganizationCreateSerializer,
    OrganizationReadSerializer,
    OrganizationUpdateSerializer,
    PositionSerializer,
    ServiceSerializer,
    SubCategorySerializer,
)
from organizations.services import (
    CategoryService,
    LevelService,
    OrganizationService,
    PositionService,
    ServiceClassificationService,
    SubCategoryService,
)


class ServiceBackedCrudViewSet(viewsets.GenericViewSet):
    """CRUD transport adapter; persistence and business rules live in services."""

    permission_classes = [OrganizationCatalogPermission]
    service_class = None
    read_serializer_class = None
    create_serializer_class = None
    update_serializer_class = None

    def get_serializer_class(self):
        if self.action == "create" and self.create_serializer_class:
            return self.create_serializer_class
        if self.action in {"update", "partial_update"} and self.update_serializer_class:
            return self.update_serializer_class
        return self.read_serializer_class or super().get_serializer_class()

    def serialize_response(self, instance, *, many=False):
        serializer_class = self.read_serializer_class or self.serializer_class
        return serializer_class(instance, many=many, context=self.get_serializer_context())

    def get_service(self):
        return self.service_class()

    def get_queryset(self):
        return self.get_service().list_queryset()

    def list(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serialize_response(page, many=True)
            return self.get_paginated_response(serializer.data)
        return Response(self.serialize_response(queryset, many=True).data)

    def retrieve(self, request, pk=None):
        instance = self.get_service().get(pk)
        return Response(self.serialize_response(instance).data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = self.get_service().create(
            data=serializer.validated_data,
            actor=request.user,
        )
        return Response(
            self.serialize_response(instance).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, pk=None, partial=False):
        current = self.get_service().get(pk)
        serializer = self.get_serializer(
            current,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        instance = self.get_service().update(
            resource_id=pk,
            data=serializer.validated_data,
            actor=request.user,
        )
        return Response(self.serialize_response(instance).data)

    def partial_update(self, request, pk=None):
        return self.update(request, pk=pk, partial=True)

    def destroy(self, request, pk=None):
        self.get_service().delete(resource_id=pk, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    create=extend_schema(
        tags=["Organizations"],
        summary="Create an organization",
        description=(
            "Create the organization first. `parent_org` is an optional existing "
            "organization ID, not a count. Assign `head_employee` later with PATCH "
            "after the employee belongs to this organization."
        ),
        request=OrganizationCreateSerializer,
        responses={201: OrganizationReadSerializer},
        examples=[
            OpenApiExample(
                "Create a ministry",
                value={
                    "name": "Ministry of Public Administration",
                    "code": "MOPA",
                    "org_type": "ministry",
                    "province": "03",
                    "address": "Hetauda, Makwanpur",
                    "established_date_ad": "2026-06-28",
                    "established_date_bs": "2083-03-14",
                    "is_active": True,
                    "parent_org": None,
                },
                request_only=True,
            )
        ],
    ),
    update=extend_schema(
        tags=["Organizations"],
        request=OrganizationUpdateSerializer,
        responses=OrganizationReadSerializer,
    ),
    partial_update=extend_schema(
        tags=["Organizations"],
        request=OrganizationUpdateSerializer,
        responses=OrganizationReadSerializer,
    ),
)
@extend_schema(tags=["Organizations"])
class OrganizationViewSet(ServiceBackedCrudViewSet):
    serializer_class = OrganizationReadSerializer
    read_serializer_class = OrganizationReadSerializer
    create_serializer_class = OrganizationCreateSerializer
    update_serializer_class = OrganizationUpdateSerializer
    service_class = OrganizationService
    filterset_fields = ["org_type", "province", "parent_org", "is_active"]
    search_fields = ["name", "code", "address"]
    ordering_fields = ["id", "name", "code", "org_type", "created_at"]
    ordering = ["name"]


@extend_schema_view(
    create=extend_schema(
        tags=["Services"],
        summary="Create a civil service",
        examples=[
            OpenApiExample(
                "Administration service",
                value={"name": "Administration Service"},
                request_only=True,
            )
        ],
    )
)
@extend_schema(tags=["Services"])
class ServiceViewSet(ServiceBackedCrudViewSet):
    serializer_class = ServiceSerializer
    service_class = ServiceClassificationService
    search_fields = ["name"]
    ordering_fields = ["id", "name"]
    ordering = ["name"]


@extend_schema_view(
    create=extend_schema(
        tags=["Categories"],
        summary="Create a service category",
        description="`service` is an ID returned by GET /api/services/.",
        examples=[
            OpenApiExample(
                "General administration category",
                value={"name": "General Administration", "service": 1},
                request_only=True,
            )
        ],
    )
)
@extend_schema(tags=["Categories"])
class CategoryViewSet(ServiceBackedCrudViewSet):
    serializer_class = CategorySerializer
    service_class = CategoryService
    filterset_fields = ["service"]
    search_fields = ["name", "service__name"]
    ordering_fields = ["id", "name", "service"]
    ordering = ["service", "name"]


@extend_schema_view(
    create=extend_schema(
        tags=["Subcategories"],
        summary="Create a service subcategory",
        description="`category` is an ID returned by GET /api/categories/.",
        examples=[
            OpenApiExample(
                "Personnel administration subcategory",
                value={"name": "Personnel Administration", "category": 1},
                request_only=True,
            )
        ],
    )
)
@extend_schema(tags=["Subcategories"])
class SubCategoryViewSet(ServiceBackedCrudViewSet):
    serializer_class = SubCategorySerializer
    service_class = SubCategoryService
    filterset_fields = ["category", "category__service"]
    search_fields = ["name", "category__name", "category__service__name"]
    ordering_fields = ["id", "name", "category"]
    ordering = ["category", "name"]


@extend_schema_view(
    create=extend_schema(
        tags=["Positions"],
        summary="Create a position",
        description=(
            "Foreign-key values are IDs from the corresponding list endpoints. "
            "Category and subcategory must belong to the selected hierarchy."
        ),
        examples=[
            OpenApiExample(
                "Personnel officer position",
                value={
                    "title": "Personnel Officer",
                    "service": 1,
                    "category": 1,
                    "subcategory": 1,
                    "level": 1,
                },
                request_only=True,
            )
        ],
    )
)
@extend_schema(tags=["Positions"])
class PositionViewSet(ServiceBackedCrudViewSet):
    serializer_class = PositionSerializer
    service_class = PositionService
    filterset_fields = ["service", "category", "subcategory", "level"]
    search_fields = [
        "title",
        "service__name",
        "category__name",
        "subcategory__name",
        "level__name",
    ]
    ordering_fields = ["id", "title", "service", "category", "level"]
    ordering = ["title"]


@extend_schema_view(
    create=extend_schema(
        tags=["Levels"],
        summary="Create an employee level",
        examples=[
            OpenApiExample(
                "Seventh level",
                value={
                    "name": "Seventh Level",
                    "gazetted_type": "NON_GAZETTED",
                },
                request_only=True,
            )
        ],
    )
)
@extend_schema(tags=["Levels"])
class LevelViewSet(ServiceBackedCrudViewSet):
    serializer_class = LevelSerializer
    service_class = LevelService
    filterset_fields = ["gazetted_type"]
    search_fields = ["name"]
    ordering_fields = ["id", "name", "gazetted_type"]
    ordering = ["name"]
