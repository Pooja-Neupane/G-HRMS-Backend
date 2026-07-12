"""Document categories and verification policies."""

from pathlib import Path

from django.db import models
from simple_history.models import HistoricalRecords

from core.models import CodeModel,SoftDeleteModel, AppendOnlyModel
from django.core.exceptions import ValidationError

from django.conf import settings
from django.core.validators import MinValueValidator,RegexValidator
from django.db.models import Q

from documents.utils import document_version_upload_path

from django.utils import timezone


class DocumentCategory(CodeModel,SoftDeleteModel):
    class Scope(models.TextChoices):
        EMPLOYEE="employee","Employee document"
        ORGANIZATION="organization","Organization document"

    class VerificationMode(models.TextChoices):
        REQUIRED = "required","Manual verification required"
        TRUSTED_UPLOADER = "trusted_uploader","Trusted uploader verification"
        NOT_REQUIRED = "not_required","verification not required"

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    scope = models.CharField(
        max_length=20,
        choices=Scope.choices,
        default=Scope.EMPLOYEE
    )

    verification_mode = models.CharField(
        max_length=24,
        choices=VerificationMode.choices,
        default=VerificationMode.REQUIRED
    )

    employee_can_upload = models.BooleanField(default=True)
    allowed_extensions = models.JSONField(
        default=list,
        blank=True,
        help_text='Example:["pdf","jpg","jpeg","png"]',
    )

    max_file_size_mb = models.PositiveSmallIntegerField(default=10)
    retention_years = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Leave empty for permanent retention.",
    )
    is_active = models.BooleanField(default=True)
    allow_multiple = models.BooleanField(
        default=False,
        help_text="Allow an employee to have multiple documents in this category."
    )

    history = HistoricalRecords()

    class Meta(SoftDeleteModel.Meta):
        ordering=["name"]
        indexes=[
            models.Index(fields=["scope","is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_scope_display()})"
    

class EmployeeDocument(CodeModel,SoftDeleteModel):
    """Logical employee document containing one or more file versions."""

    class LifecycleStatus(models.TextChoices):
        ACTIVE = "active","Active"
        ARCHIVED = "archived","Archived"
        REVOKED = "revoked","Revoked"

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="employee_documents",
    )

    category = models.ForeignKey(
        DocumentCategory,
        on_delete=models.PROTECT,
        related_name="employee_documents",        
    )
    title = models.CharField(max_length=160)
    document_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="Certificate,citizenship,order,or reference number."

    )

    issued_by = models.CharField(max_length=160,blank=True)
    issue_date_ad = models.DateField(null=True,blank=True)
    issue_date_bs = models.CharField(max_length=10,blank=True)

    expiry_date_ad = models.DateField(null=True,blank=True)
    expiry_date_bs = models.CharField(max_length=10,blank=True)

    lifecycle_status = models.CharField(
        max_length=12,
        choices=LifecycleStatus.choices,
        default= LifecycleStatus.ACTIVE
    )

    remarks = models.TextField(blank=True)
    history = HistoricalRecords()


    class Meta(SoftDeleteModel.Meta):
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=["employee","category"]),
            models.Index(fields=["employee","lifecycle_status"]),
        ]

    def clean(self):
        super().clean()
        errors={}

        if(
            self.category_id
            and self.category.scope != DocumentCategory.Scope.EMPLOYEE
        ):
            errors["category"] = (
                "Only employee-scoped categories can be assigned to employees."
            )

        if (
            self.issue_date_ad
            and self.expiry_date_ad
            and self.expiry_date_ad < self.issue_date_ad
        ):
            errors["expiry_date_ad"] = (
                "Expiry date cannot be before the issue date."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.employee} - {self.title}"
    
class DocumentVersion(SoftDeleteModel):
    """Immutable uploaded file metadata with version-specific verification."""

    class UploadSource(models.TextChoices):
        EMPLOYEE = "employee","Employee"
        HR = "hr","HR personnel"
        SYSTEM = "system","System generated"

    class VerificationStatus(models.TextChoices):
        PENDING = "pending","Pending"
        IN_REVIEW = "in_review","In review"
        VERIFIED = "verified","Verified"
        REJECTED = "rejected","Rejected"
        NOT_REQUIRED = "not_required","Not required"

    class ScanStatus(models.TextChoices):
        PENDING = "pending","Pending"
        CLEAN = "clean","Clean"
        INFECTED = "infected","Infected"
        FAILED = "failed","Scan failed"

    document = models.ForeignKey(
        EmployeeDocument,
        on_delete=models.PROTECT,
        related_name="versions",
    )

    version_number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)]
    )

    file = models.FileField(
        upload_to=document_version_upload_path,
        max_length=500
    )

    original_file_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    file_size_bytes = models.PositiveBigIntegerField(
        validators=[MinValueValidator(1)],
    )
    file_hash_sha256 = models.CharField(
        max_length=64,
        validators=[
            RegexValidator(
                regex=r"^[a-f0-9]{64}$",
                message="Enter a lowercase SHA-256 hexadecimal hash.",
            )
        ],
    )

    upload_source = models.CharField(
        max_length=12,
        choices=UploadSource.choices,
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_document_versions",
    )

    verification_status = models.CharField(
        max_length=16,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING
    )

    scan_status= models.CharField(
        max_length=12,
        choices=ScanStatus.choices,
        default=ScanStatus.PENDING,
    )

    is_current = models.BooleanField(default=True)

    history = HistoricalRecords()


    class Meta(SoftDeleteModel.Meta):
        ordering = ["document","-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["document","version_number"],
                name="unique_document_version_number",
            ),
            models.UniqueConstraint(
                fields=["document"],
                condition=Q(is_current=True,is_deleted=False),
                name="one_current_version_per_document"
            ),
        ]

        indexes = [
            models.Index(fields=["document","is_current"]),
            models.Index(fields=["verification_status"]),
            models.Index(fields=["scan_status"]),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.document_id:
            category = self.document.category
            maximum_bytes = category.max_file_size_mb * 1024 * 1024

            if self.file_size_bytes and self.file_size_bytes > maximum_bytes:
                errors["file"] = (
                    f"File cannot exceed {category.max_file_size_mb} MB."
                    
                )

            extension = Path(self.original_file_name).suffix.lower().lstrip(".")
            allowed = {
                value.lower().lstrip(".")
                for value in category.allowed_extensions
            }

            if allowed and extension not in allowed:
                errors["file"] = (
                    f"Allowed extensions: {', '.join(sorted(allowed))}."
                )

            if not self._state.adding:
                original = type(self).all_objects.filter(pk=self.pk).first()

                if original:
                    immutable_fields = {
                        "document":(
                            original.document_id,
                            self.document_id,
                        ),

                        "version_number":(
                            original.version_number,
                            self.version_number
                        ),

                        "file":(
                            original.file.name,
                            self.file.name,
                        ),
                        "file_hash_sha256":(
                            original.file_hash_sha256,
                            self.file_hash_sha256
                        ),
                        "file_size_bytes":(
                            original.file_size_bytes,
                            self.file_size_bytes,
                        ),
                        "original_file_name": (
                            original.original_file_name,
                            self.original_file_name,
                        ),
                        "content_type": (
                            original.content_type,
                            self.content_type,
                        ),
                        "upload_source": (
                            original.upload_source,
                            self.upload_source,
                        ),
                        "uploaded_by": (
                            original.uploaded_by_id,
                            self.uploaded_by_id,
                        ),
                                            
                    }


                    for field,(old_value,new_value) in immutable_fields.items():
                        if old_value != new_value:
                            errors[field] = (
                                "Uploaded file metadata cannot be changed. "
                                "Create a new version instead."
                            )

            if errors:
                raise ValidationError(errors)
    def __str__(self):
        return (
            f"{self.document}"
            f"(version {self.version_number})"
        )


class DocumentVerification(AppendOnlyModel):
    """Immutable verification decision for one exact file version"""

    class Decision(models.TextChoices):
        VERIFIED= "verified","Verified"
        REJECTED = "rejected","Rejected"


    version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.PROTECT,
        related_name="verification_events",
    )

    decision= models.CharField(
        max_length=12,
        choices=Decision.choices

    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="document_verifications",
    )

    reviewed_at = models.DateTimeField(default=timezone.now, editable=False)
    file_hash_sha256 = models.CharField(
        max_length=64,
        validators=[
            RegexValidator(
                regex=r"^[a-f0-9]{64}$",
                message = "Enter a lowercase SHA-256 hexadecimal hash.",
            )
        ],
    )

    remarks = models.TextField(blank=True)
    checklist = models.JSONField(default=dict,blank=True)


    class Meta(AppendOnlyModel.Meta):
        ordering = ["-reviewed_at"]
        indexes=[
            models.Index(fields=["version","reviewed_at"]),
            models.Index(fields=["decision","reviewed_at"])
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.version_id:
            if self.file_hash_sha256 != self.version.file_hash_sha256:
                errors["file_hash_sha256"] = (
                    "Verification hash must match the uploaded file version."
                )
            if (
                self.decision == self.Decision.VERIFIED
                and self.version.scan_status != DocumentVersion.ScanStatus.CLEAN
            ):
                errors["decision"] = (
                    "A document can be verified only after a clean malware scan."
                )

            if not self.version.is_current or self.version.is_deleted:
                errors["version"] = (
                    "Only the current active document version can be reviewed."
                )

        if (
            self.decision == self.Decision.REJECTED and not self.remarks.strip()
        ):
            errors["remarks"] = (
                "Remarks are required when rejecting a document."
            )

        if errors:
            raise ValidationError(errors)
        

    def __str__(self):
        return f"{self.version} - {self.get_decision_display()}"
        
