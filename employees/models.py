from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from core.models import AppendOnlyModel, BigAutoSoftDeleteModel, SoftDeleteModel
from organizations.models import Level, Organization, OrganizationPosition, Position


class Employee(BigAutoSoftDeleteModel):
    class Status(models.TextChoices):
        IN_SERVICE = "IN_SERVICE", "In Service"
        SUSPENDED = "SUSPENDED", "Suspended"
        IN_LEAVE = "IN_LEAVE", "In Leave"
        RETIRED = "RETIRED", "Retired"
        TERMINATED = "TERMINATED", "Terminated"
        DECEASED = "DECEASED", "Deceased"

    class EmploymentType(models.TextChoices):
        PERMANENT = "permanent", "Permanent"
        CONTRACT = "contract", "Contract"
        PROBATIONARY = "probationary", "Probationary"
        DEPUTATION = "deputation", "Deputation"

    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=50, blank=True, null=True)
    last_name = models.CharField(max_length=100)
    father_name = models.CharField(max_length=100, blank=True, null=True)
    grandfather_name = models.CharField(max_length=100, blank=True, null=True)
    spouse_name = models.CharField(max_length=100, blank=True, null=True)
    beneficiary_name = models.CharField(max_length=100, blank=True, null=True)
    permanent_address = models.CharField(max_length=255, null=True, blank=True)
    ka_sa_num = models.CharField(max_length=100, unique=True)
    citizenship_number = models.CharField(
        max_length=50, unique=True, null=True, blank=True
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )
    level = models.ForeignKey(
        Level,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_SERVICE,
    )
    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.PERMANENT,
    )
    gender = models.CharField(
        choices=[("Male", "पुरुष"), ("Female", "महिला"), ("Other", "अन्य")],
        max_length=20,
        blank=True,
        null=True,
    )
    gender_other = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Specify gender if 'Other' is selected.",
    )
    dob_bs = models.CharField(max_length=10)
    dob_ad = models.DateField()

    jobstartdate_bs = models.CharField(max_length=10)
    jobstartdate_ad = models.DateField()
    current_position_date_bs = models.CharField(max_length=10)
    current_position_date_ad = models.DateField()

    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)

    working_organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        related_name="employees",
    )
    supervisor = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="direct_reports",
    )
    remarks = models.TextField(blank=True)
    photo = models.ImageField(upload_to="employee_photos/", blank=True, null=True)

    # --- NEW audit tracking fields ---
    initiated_by = models.ForeignKey(  # transfer initiator
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="initiated_employee_updates",
    )
    history = HistoricalRecords()

    class Meta(BigAutoSoftDeleteModel.Meta):
        indexes = [models.Index(fields=["working_organization", "status"])]

    @property
    def full_name(self):
        return " ".join(
            part for part in (self.first_name, self.middle_name, self.last_name) if part
        )

    def clean(self):
        super().clean()
        errors = {}
        if self.gender == "Other" and not self.gender_other:
            errors["gender_other"] = "Specify the gender when 'Other' is selected."
        elif self.gender != "Other" and self.gender_other:
            errors["gender_other"] = (
                "Gender details are allowed only when gender is 'Other'."
            )

        if self.dob_ad and self.jobstartdate_ad and self.dob_ad >= self.jobstartdate_ad:
            errors["jobstartdate_ad"] = "Joining date must be after date of birth."
        if (
            self.jobstartdate_ad
            and self.current_position_date_ad
            and self.current_position_date_ad < self.jobstartdate_ad
        ):
            errors["current_position_date_ad"] = (
                "Current position date cannot be before joining date."
            )

        if self.position_id and self.level_id:
            position_level_id = self.position.level_id
            if position_level_id and position_level_id != self.level_id:
                errors["level"] = "Employee level must match the selected position level."

        if self.working_organization_id and self.position_id:
            sanctioned = OrganizationPosition.objects.filter(
                organization_id=self.working_organization_id,
                is_active=True,
            )
            if sanctioned.exists() and not sanctioned.filter(
                position_id=self.position_id
            ).exists():
                errors["position"] = (
                    "This position is not sanctioned for the selected organization."
                )

        if (
            self.status == self.Status.IN_SERVICE
            and self.working_organization_id
            and not self.working_organization.is_active
        ):
            errors["working_organization"] = (
                "An in-service employee must belong to an active organization."
            )

        if self.supervisor_id:
            if self.pk is not None and self.supervisor_id == self.pk:
                errors["supervisor"] = "An employee cannot supervise themselves."
            else:
                manager = self.supervisor
                visited = set()
                while manager is not None:
                    if manager.pk == self.pk or manager.pk in visited:
                        errors["supervisor"] = (
                            "This supervisor would create a reporting cycle."
                        )
                        break
                    visited.add(manager.pk)
                    manager = manager.supervisor

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.full_name


class EmployeeContact(SoftDeleteModel):
    class Kind(models.TextChoices):
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"
        ADDRESS = "address", "Address"
        EMERGENCY = "emergency", "Emergency"
        BANK = "bank", "Bank"

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="contacts",
    )
    kind = models.CharField(max_length=12, choices=Kind.choices)
    value = models.CharField(max_length=255)
    is_primary = models.BooleanField(default=False)
    verified = models.BooleanField(default=False)
    history = HistoricalRecords()

    class Meta(SoftDeleteModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "kind"],
                condition=models.Q(is_primary=True, is_deleted=False),
                name="one_primary_contact_per_kind",
            )
        ]

    def __str__(self):
        return f"{self.employee} - {self.get_kind_display()}"


class ServiceBookEntry(AppendOnlyModel):
    class EntryType(models.TextChoices):
        APPOINTMENT = "appointment", "Appointment"
        PROMOTION = "promotion", "Promotion"
        TRANSFER = "transfer", "Transfer"
        GRADE_CHANGE = "grade_change", "Grade change"
        STATUS_CHANGE = "status_change", "Status change"

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="service_book_entries",
    )
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    field_name = models.CharField(max_length=64, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    effective_date = models.DateField()
    order_reference = models.CharField(max_length=64, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_service_book_entries",
    )
    remarks = models.TextField(blank=True)

    class Meta(AppendOnlyModel.Meta):
        ordering = ["-effective_date", "-created_at"]
        indexes = [models.Index(fields=["employee", "effective_date"])]

    def __str__(self):
        return f"{self.employee} - {self.get_entry_type_display()}"


class EmployeeStatusHistory(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    changed_on = models.DateField(auto_now_add=True)
    remarks = models.CharField(max_length=200, blank=True, null=True)


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        HALF_DAY = "half_day", "Half Day"
        HOLIDAY = "holiday", "Holiday"

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    work_date = models.DateField()
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PRESENT,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-work_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "work_date"],
                name="unique_attendance_per_employee_day",
            )
        ]

    def __str__(self):
        return f"{self.employee} - {self.work_date}"


class LeaveRequest(models.Model):
    class LeaveType(models.TextChoices):
        SICK = "sick", "Sick"
        ANNUAL = "annual", "Annual"
        PERSONAL = "personal", "Personal"
        MATERNITY = "maternity", "Maternity"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="leave_requests",
    )
    leave_type = models.CharField(max_length=20, choices=LeaveType.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_leave_requests",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date cannot be before start date."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def total_days(self):
        return (self.end_date - self.start_date).days + 1

    def __str__(self):
        return f"{self.employee} - {self.leave_type} ({self.status})"


class OfficeTransfer(models.Model):
    class Status(models.TextChoices):
        TRANSFERRED = "TRANSFERRED", "सरुवा"
        KAAJ = "KAAJ", "काज"
        PROMOTED = "PROMOTED", "बढुवा"
        RECRUITED = "RECRUITED", "नियुक्ति"
        OTHER = "OTHER", "अन्य"

    employee = models.ForeignKey("employees.Employee", on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TRANSFERRED,
    )
    to_organization = models.ForeignKey(
        "organizations.Organization",
        related_name="transfers_to",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    to_date_ad = models.DateField(
        null=True, blank=True
    )  # null means currently working here
    to_date_bs = models.CharField(max_length=10, null=True, blank=True)

    decision_date_ad = models.DateField(null=True, blank=True)
    decision_date_bs = models.CharField(max_length=10, null=True, blank=True)
    # --- NEW audit tracking fields ---
    initiated_by = models.ForeignKey(  # transfer initiator
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="initiated_transfers",
    )
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(  # verifier (Kitabkhana)
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verified_transfers",
    )
    verified_on = models.DateTimeField(null=True, blank=True)

    remarks = models.TextField(blank=True, null=True)

    def __str__(self):
        current = " (current)" if not self.to_date_ad else ""
        return f"{self.employee} → {self.to_organization}{current}"
