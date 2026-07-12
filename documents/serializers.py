"""Transport validation and response representations for document APIs."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from documents.models import (
    DocumentCategory,
    DocumentVerification,
    DocumentVersion,
    EmployeeDocument,
)
from employees.models import Employee


class DocumentEmployeeReferenceSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Employee
        fields = ("id", "ka_sa_num", "full_name")


class DocumentCategoryReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentCategory
        fields = ("id", "code", "name", "scope", "verification_mode")


class DocumentVersionUploadSerializer(serializers.Serializer):
    """Client-supplied upload payload; all other metadata is server-derived."""

    file = serializers.FileField()
    upload_source = serializers.ChoiceField(
        choices=DocumentVersion.UploadSource.choices
    )


class DocumentVersionReadSerializer(serializers.ModelSerializer):
    upload_source_display = serializers.CharField(
        source="get_upload_source_display", read_only=True
    )
    verification_status_display = serializers.CharField(
        source="get_verification_status_display", read_only=True
    )
    scan_status_display = serializers.CharField(
        source="get_scan_status_display", read_only=True
    )
    uploaded_by_id = serializers.IntegerField(read_only=True, allow_null=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = DocumentVersion
        fields = (
            "id",
            "version_number",
            "is_current",
            "original_file_name",
            "content_type",
            "file_size_bytes",
            "file_hash_sha256",
            "upload_source",
            "upload_source_display",
            "verification_status",
            "verification_status_display",
            "scan_status",
            "scan_status_display",
            "uploaded_by_id",
            "download_url",
            "created_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_download_url(self, obj):
        if not obj.file:
            return None
        url = obj.file.url
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url


class EmployeeDocumentReadSerializer(serializers.ModelSerializer):
    employee = DocumentEmployeeReferenceSerializer(read_only=True)
    category = DocumentCategoryReferenceSerializer(read_only=True)
    lifecycle_status_display = serializers.CharField(
        source="get_lifecycle_status_display", read_only=True
    )
    current_version = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeDocument
        fields = (
            "id",
            "code",
            "employee",
            "category",
            "title",
            "document_number",
            "issued_by",
            "issue_date_ad",
            "issue_date_bs",
            "expiry_date_ad",
            "expiry_date_bs",
            "lifecycle_status",
            "lifecycle_status_display",
            "remarks",
            "current_version",
            "created_at",
        )
        read_only_fields = fields

    @extend_schema_field(DocumentVersionReadSerializer(allow_null=True))
    def get_current_version(self, obj):
        version = obj.versions.filter(is_current=True).first()
        if version is None:
            return None
        return DocumentVersionReadSerializer(version, context=self.context).data


class EmployeeDocumentWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeDocument
        fields = (
            "code",
            "employee",
            "category",
            "title",
            "document_number",
            "issued_by",
            "issue_date_ad",
            "issue_date_bs",
            "expiry_date_ad",
            "expiry_date_bs",
            "lifecycle_status",
            "remarks",
        )


class EmployeeDocumentSubmitSerializer(serializers.ModelSerializer):
    """One-shot upload: document metadata plus the file, in one multipart call.

    ``code`` is server-generated and ``upload_source`` is derived from the
    caller, so the client supplies neither.
    """

    file = serializers.FileField(write_only=True)

    class Meta:
        model = EmployeeDocument
        fields = (
            "employee",
            "category",
            "title",
            "document_number",
            "issued_by",
            "issue_date_ad",
            "issue_date_bs",
            "expiry_date_ad",
            "expiry_date_bs",
            "remarks",
            "file",
        )


class DocumentScanResultSerializer(serializers.Serializer):
    """Completed malware-scan outcome reported by the scanner."""

    scan_status = serializers.ChoiceField(
        choices=[
            (value, label)
            for value, label in DocumentVersion.ScanStatus.choices
            if value != DocumentVersion.ScanStatus.PENDING
        ]
    )


class DocumentVerificationCreateSerializer(serializers.Serializer):
    """Reviewer decision; the file hash and reviewer are server-derived."""

    decision = serializers.ChoiceField(
        choices=DocumentVerification.Decision.choices
    )
    remarks = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    checklist = serializers.JSONField(required=False, default=dict)


class DocumentVerificationReadSerializer(serializers.ModelSerializer):
    decision_display = serializers.CharField(
        source="get_decision_display", read_only=True
    )
    reviewed_by_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = DocumentVerification
        fields = (
            "id",
            "version",
            "decision",
            "decision_display",
            "reviewed_by_id",
            "reviewed_at",
            "file_hash_sha256",
            "remarks",
            "checklist",
        )
        read_only_fields = fields
