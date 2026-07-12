"""HTTP adapters for employee and office-transfer APIs."""

from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.response import Response

from employees.filters import EmployeeFilter
from employees.models import OfficeTransfer
from employees.permissions import EmployeePermission
from employees.serializers import (
    EmployeeCreateSerializer,
    EmployeeReadSerializer,
    EmployeeWriteSerializer,
    OfficeTransferSerializer,
)
from employees.services import EmployeeService


@extend_schema_view(
    create=extend_schema(
        tags=["Employees"],
        summary="Create an employee",
        description=(
            "Foreign-key values are IDs from the organization, position, level, "
            "and employee list endpoints. Recruitment history is created "
            "transactionally when an organization is supplied."
        ),
        request=EmployeeCreateSerializer,
        responses={201: EmployeeReadSerializer},
        examples=[
            OpenApiExample(
                "Create an employee",
                value={
                    "ka_sa_num": "EMP-10241",
                    "first_name": "Sita",
                    "middle_name": "Kumari",
                    "last_name": "Shrestha",
                    "father_name": "Ram Shrestha",
                    "grandfather_name": "Hari Shrestha",
                    "spouse_name": "Bikash Shrestha",
                    "beneficiary_name": "Aarav Shrestha",
                    "permanent_address": "Hetauda, Makwanpur",
                    "citizenship_number": "31-01-75-12345",
                    "gender": "Female",
                    "gender_other": None,
                    "dob_bs": "2050-01-01",
                    "dob_ad": "1993-04-14",
                    "email": "sita.shrestha@example.gov.np",
                    "phone_number": "+9779812345678",
                    "employment_type": "permanent",
                    "status": "IN_SERVICE",
                    "jobstartdate_bs": "2080-01-01",
                    "jobstartdate_ad": "2023-04-14",
                    "current_position_date_bs": "2080-01-01",
                    "current_position_date_ad": "2023-04-14",
                    "working_organization": 1,
                    "position": 1,
                    "level": 1,
                    "supervisor": None,
                    "remarks": "Initial appointment",
                },
                request_only=True,
            )
        ],
    ),
    update=extend_schema(
        tags=["Employees"],
        request=EmployeeWriteSerializer,
        responses=EmployeeReadSerializer,
    ),
    partial_update=extend_schema(
        tags=["Employees"],
        request=EmployeeWriteSerializer,
        responses=EmployeeReadSerializer,
        examples=[
            OpenApiExample(
                "Change status",
                value={"status": "IN_LEAVE"},
                request_only=True,
            )
        ],
    ),
)
@extend_schema(tags=["Employees"])
class EmployeeViewSet(viewsets.GenericViewSet):
    permission_classes = [EmployeePermission]
    serializer_class = EmployeeReadSerializer
    filterset_class = EmployeeFilter
    search_fields = [
        "first_name",
        "middle_name",
        "last_name",
        "email",
        "citizenship_number",
        "ka_sa_num",
        "working_organization__name",
    ]
    ordering_fields = [
        "id",
        "first_name",
        "last_name",
        "ka_sa_num",
        "jobstartdate_ad",
        "created_at",
    ]
    ordering = ["first_name", "last_name"]
    service_class = EmployeeService

    def get_service(self):
        return self.service_class()

    def get_queryset(self):
        return self.get_service().list_queryset()

    def get_serializer_class(self):
        if self.action == "create":
            return EmployeeCreateSerializer
        if self.action in {"update", "partial_update"}:
            return EmployeeWriteSerializer
        return EmployeeReadSerializer

    def serialize_response(self, employee, *, many=False):
        return EmployeeReadSerializer(
            employee,
            many=many,
            context=self.get_serializer_context(),
        )

    def list(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serialize_response(page, many=True)
            return self.get_paginated_response(serializer.data)
        return Response(self.serialize_response(queryset, many=True).data)

    def retrieve(self, request, pk=None):
        employee = self.get_service().get(pk)
        return Response(self.serialize_response(employee).data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = self.get_service().create(
            data=serializer.validated_data,
            actor=request.user,
        )
        return Response(
            self.serialize_response(employee).data,
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
        employee = self.get_service().update(
            employee_id=pk,
            data=serializer.validated_data,
            actor=request.user,
        )
        return Response(self.serialize_response(employee).data)

    def partial_update(self, request, pk=None):
        return self.update(request, pk=pk, partial=True)

    def destroy(self, request, pk=None):
        self.get_service().delete(employee_id=pk, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Office Transfers"])
class OfficeTransferViewSet(viewsets.ModelViewSet):
    permission_classes = [EmployeePermission]
    queryset = OfficeTransfer.objects.select_related(
        "employee", "to_organization", "initiated_by", "verified_by"
    )
    serializer_class = OfficeTransferSerializer
    filterset_fields = ["employee", "to_organization", "status", "verified"]
    search_fields = ["employee__ka_sa_num", "employee__first_name", "remarks"]
    ordering_fields = ["id", "decision_date_ad", "to_date_ad"]
    ordering = ["-id"]

    def perform_create(self, serializer):
        serializer.save(initiated_by=self.request.user)
