"""HTTP adapters for employee document and file-version APIs."""

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from documents.exceptions import (
    DocumentNotFoundError,
    DocumentVersionNotFoundError,
)
from documents.models import DocumentVersion
from documents.permissions import DocumentPermission
from documents.repositories import (
    DocumentVerificationRepository,
    DocumentVersionRepository,
    EmployeeDocumentRepository,
)
from documents.serializers import (
    DocumentScanResultSerializer,
    DocumentVerificationCreateSerializer,
    DocumentVerificationReadSerializer,
    DocumentVersionReadSerializer,
    DocumentVersionUploadSerializer,
    EmployeeDocumentReadSerializer,
    EmployeeDocumentSubmitSerializer,
    EmployeeDocumentWriteSerializer,
)
from authentication.permissions import IsSuperAdmin
from documents.services import (
    DocumentScanService,
    DocumentUploadService,
    DocumentVerificationService,
    EmployeeDocumentService,
)


@extend_schema(tags=["Documents"])
@extend_schema_view(
    list=extend_schema(summary="List employee documents"),
    retrieve=extend_schema(summary="Retrieve an employee document"),
    create=extend_schema(
        summary="Submit a document (upload file + metadata in one call)",
        description=(
            "Uploads a document in a single multipart request. If the employee "
            "already has an active document in a single-instance category, a new "
            "file version is appended to it; otherwise a new document is created "
            "with a server-generated code. The upload source is derived from the "
            "caller's role."
        ),
        request={"multipart/form-data": EmployeeDocumentSubmitSerializer},
        responses={201: EmployeeDocumentReadSerializer},
    ),
    update=extend_schema(
        request=EmployeeDocumentWriteSerializer,
        responses=EmployeeDocumentReadSerializer,
    ),
    partial_update=extend_schema(
        request=EmployeeDocumentWriteSerializer,
        responses=EmployeeDocumentReadSerializer,
    ),
)
class EmployeeDocumentViewSet(viewsets.GenericViewSet):
    permission_classes = [DocumentPermission]
    serializer_class = EmployeeDocumentReadSerializer
    filterset_fields = ["employee", "category", "lifecycle_status"]
    search_fields = ["title", "document_number", "code"]
    ordering_fields = ["id", "created_at", "title"]
    ordering = ["-created_at"]

    version_repository_class = DocumentVersionRepository
    document_service_class = EmployeeDocumentService
    upload_service_class = DocumentUploadService

    def get_document_service(self):
        return self.document_service_class()

    def get_version_repository(self):
        return self.version_repository_class()

    def get_queryset(self):
        return self.get_document_service().list_queryset()

    def get_serializer_class(self):
        if self.action == "create":
            return EmployeeDocumentSubmitSerializer
        if self.action in {"update", "partial_update"}:
            return EmployeeDocumentWriteSerializer
        return EmployeeDocumentReadSerializer

    @staticmethod
    def _upload_source_for(user):
        is_privileged = user.is_superuser or user.role in {
            user.Role.SUPERADMIN,
            user.Role.HR_PERSONNEL,
        }
        return (
            DocumentVersion.UploadSource.HR
            if is_privileged
            else DocumentVersion.UploadSource.EMPLOYEE
        )

    def serialize_document(self, instance, *, many=False):
        return EmployeeDocumentReadSerializer(
            instance,
            many=many,
            context=self.get_serializer_context(),
        )

    def list(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serialize_document(page, many=True)
            return self.get_paginated_response(serializer.data)
        return Response(self.serialize_document(queryset, many=True).data)

    def retrieve(self, request, pk=None):
        document = self.get_document_service().get(pk)
        return Response(self.serialize_document(document).data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = self.get_document_service().submit(
            data=serializer.validated_data,
            actor=request.user,
            upload_source=self._upload_source_for(request.user),
        )
        return Response(
            self.serialize_document(document).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, pk=None, partial=False):
        current = self.get_document_service().get(pk)
        serializer = self.get_serializer(
            current, data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        document = self.get_document_service().update(
            document_id=pk,
            data=serializer.validated_data,
            actor=request.user,
        )
        return Response(self.serialize_document(document).data)

    def partial_update(self, request, pk=None):
        return self.update(request, pk=pk, partial=True)

    def destroy(self, request, pk=None):
        self.get_document_service().delete(document_id=pk, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        methods=["GET"],
        summary="List file versions for a document",
        responses={200: DocumentVersionReadSerializer(many=True)},
    )
    @extend_schema(
        methods=["POST"],
        summary="Upload a new file version",
        request={"multipart/form-data": DocumentVersionUploadSerializer},
        responses={201: DocumentVersionReadSerializer},
    )
    @action(
        detail=True,
        methods=["get", "post"],
        url_path="versions",
        parser_classes=[MultiPartParser, FormParser],
    )
    def versions(self, request, pk=None):
        if request.method == "POST":
            return self._upload_version(request, pk)
        return self._list_versions(request, pk)

    def _list_versions(self, request, pk):
        # Confirm the document exists (and 404 otherwise) before listing.
        self.get_document_service().get(pk)
        queryset = (
            self.get_version_repository().queryset().filter(document_id=pk)
        )
        serializer = DocumentVersionReadSerializer(
            queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    def _upload_version(self, request, pk):
        serializer = DocumentVersionUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        version = self.upload_service_class().upload_new_version(
            document_id=pk,
            uploaded_file=serializer.validated_data["file"],
            upload_source=serializer.validated_data["upload_source"],
            actor=request.user,
        )
        return Response(
            DocumentVersionReadSerializer(
                version,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Documents"])
@extend_schema_view(
    retrieve=extend_schema(summary="Retrieve a document file version"),
)
class DocumentVersionViewSet(viewsets.GenericViewSet):
    permission_classes = [DocumentPermission]
    serializer_class = DocumentVersionReadSerializer
    # Declared only so the schema generator can resolve the model and UUID pk;
    # reads go through the repository in get_object().
    queryset = DocumentVersion.objects.none()

    version_repository_class = DocumentVersionRepository
    verification_repository_class = DocumentVerificationRepository
    scan_service_class = DocumentScanService
    verification_service_class = DocumentVerificationService

    def get_version_repository(self):
        return self.version_repository_class()

    def get_object(self):
        version = self.get_version_repository().get_by_id(self.kwargs["pk"])
        if version is None:
            raise DocumentVersionNotFoundError()
        self.check_object_permissions(self.request, version)
        return version

    def retrieve(self, request, pk=None):
        version = self.get_object()
        return Response(
            DocumentVersionReadSerializer(
                version, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(
        summary="Record a completed malware-scan result (internal/admin)",
        description=(
            "Superadmin-only. Used by the scanner integration as a callback, or "
            "by an admin to override/re-scan. Normal uploads are scanned "
            "automatically; employees and HR never call this directly."
        ),
        request=DocumentScanResultSerializer,
        responses={200: DocumentVersionReadSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="scan",
        permission_classes=[IsSuperAdmin],
    )
    def scan(self, request, pk=None):
        serializer = DocumentScanResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        version = self.scan_service_class().record_result(
            version_id=pk,
            scan_status=serializer.validated_data["scan_status"],
            actor=request.user,
        )
        return Response(
            DocumentVersionReadSerializer(
                version, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(
        summary="Record a verification decision for a version",
        request=DocumentVerificationCreateSerializer,
        responses={201: DocumentVerificationReadSerializer},
    )
    @action(detail=True, methods=["post"], url_path="verify")
    def verify(self, request, pk=None):
        serializer = DocumentVerificationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        verification = self.verification_service_class().record_decision(
            version_id=pk,
            decision=serializer.validated_data["decision"],
            remarks=serializer.validated_data.get("remarks", ""),
            checklist=serializer.validated_data.get("checklist", {}),
            actor=request.user,
        )
        return Response(
            DocumentVerificationReadSerializer(
                verification, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="List verification events for a version",
        responses={200: DocumentVerificationReadSerializer(many=True)},
    )
    @action(detail=True, methods=["get"], url_path="verifications")
    def verifications(self, request, pk=None):
        self.get_object()
        queryset = self.verification_repository_class().list_for_version(pk)
        serializer = DocumentVerificationReadSerializer(
            queryset, many=True, context=self.get_serializer_context()
        )
        return Response(serializer.data)
