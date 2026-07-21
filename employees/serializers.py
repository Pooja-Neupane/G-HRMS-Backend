"""Transport validation and response representations for employee APIs."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from employees.models import AttendanceRecord, Employee, LeaveRequest, OfficeTransfer
from organizations.models import Level, Organization, Position


class EmployeeOrganizationReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("id", "code", "name")


class EmployeePositionReferenceSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source="service.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    subcategory_name = serializers.CharField(
        source="subcategory.name", read_only=True
    )

    class Meta:
        model = Position
        fields = (
            "id",
            "title",
            "service_id",
            "service_name",
            "category_id",
            "category_name",
            "subcategory_id",
            "subcategory_name",
            "level_id",
        )


class EmployeeLevelReferenceSerializer(serializers.ModelSerializer):
    gazetted_type_display = serializers.CharField(
        source="get_gazetted_type_display", read_only=True
    )

    class Meta:
        model = Level
        fields = ("id", "name", "gazetted_type", "gazetted_type_display")


class SupervisorReferenceSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Employee
        fields = ("id", "ka_sa_num", "full_name")


class EmployeeReadSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    employment_type_display = serializers.CharField(
        source="get_employment_type_display", read_only=True
    )
    gender_display = serializers.CharField(source="get_gender_display", read_only=True)
    working_organization_id = serializers.IntegerField(read_only=True, allow_null=True)
    working_organization = EmployeeOrganizationReferenceSerializer(read_only=True)
    position_id = serializers.IntegerField(read_only=True, allow_null=True)
    position = EmployeePositionReferenceSerializer(read_only=True)
    level_id = serializers.IntegerField(read_only=True, allow_null=True)
    level = EmployeeLevelReferenceSerializer(read_only=True)
    supervisor_id = serializers.IntegerField(read_only=True, allow_null=True)
    supervisor = SupervisorReferenceSerializer(read_only=True)

    class Meta:
        model = Employee
        fields = (
            "id",
            "ka_sa_num",
            "first_name",
            "middle_name",
            "last_name",
            "full_name",
            "father_name",
            "grandfather_name",
            "spouse_name",
            "beneficiary_name",
            "permanent_address",
            "citizenship_number",
            "gender",
            "gender_display",
            "gender_other",
            "dob_bs",
            "dob_ad",
            "email",
            "phone_number",
            "employment_type",
            "employment_type_display",
            "status",
            "status_display",
            "jobstartdate_bs",
            "jobstartdate_ad",
            "current_position_date_bs",
            "current_position_date_ad",
            "working_organization_id",
            "working_organization",
            "position_id",
            "position",
            "level_id",
            "level",
            "supervisor_id",
            "supervisor",
            "remarks",
            "photo",
            "initiated_by",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "row_version",
        )
        read_only_fields = fields


class EmployeeWriteSerializer(serializers.ModelSerializer):
    dob_bs = serializers.RegexField(
        r"^\d{4}-\d{2}-\d{2}$",
        max_length=10,
        help_text="Bikram Sambat date of birth in YYYY-MM-DD format.",
    )
    jobstartdate_bs = serializers.RegexField(
        r"^\d{4}-\d{2}-\d{2}$",
        max_length=10,
        help_text="Bikram Sambat joining date in YYYY-MM-DD format.",
    )
    current_position_date_bs = serializers.RegexField(
        r"^\d{4}-\d{2}-\d{2}$",
        max_length=10,
        help_text="Bikram Sambat current-position date in YYYY-MM-DD format.",
    )
    phone_number = serializers.RegexField(
        r"^\+?[0-9]{7,15}$",
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Optional phone number containing 7-15 digits and optional + prefix.",
    )
    working_organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.filter(is_active=True),
        required=True,
        allow_null=False,
        help_text="Active organization ID from GET /api/organizations/.",
    )
    position = serializers.PrimaryKeyRelatedField(
        queryset=Position.objects.all(),
        required=False,
        allow_null=True,
        help_text="Position ID from GET /api/positions/.",
    )
    level = serializers.PrimaryKeyRelatedField(
        queryset=Level.objects.all(),
        required=False,
        allow_null=True,
        help_text="Level ID from GET /api/levels/.",
    )
    supervisor = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(),
        required=False,
        allow_null=True,
        help_text="Optional supervisor employee ID from GET /api/employees/.",
    )

    class Meta:
        model = Employee
        fields = (
            "ka_sa_num",
            "first_name",
            "middle_name",
            "last_name",
            "father_name",
            "grandfather_name",
            "spouse_name",
            "beneficiary_name",
            "permanent_address",
            "citizenship_number",
            "gender",
            "gender_other",
            "dob_bs",
            "dob_ad",
            "email",
            "phone_number",
            "employment_type",
            "status",
            "jobstartdate_bs",
            "jobstartdate_ad",
            "current_position_date_bs",
            "current_position_date_ad",
            "working_organization",
            "position",
            "level",
            "supervisor",
            "remarks",
            "photo",
        )
        extra_kwargs = {
            "middle_name": {"required": False, "allow_null": True},
            "father_name": {"required": False, "allow_null": True},
            "grandfather_name": {"required": False, "allow_null": True},
            "spouse_name": {"required": False, "allow_null": True},
            "beneficiary_name": {"required": False, "allow_null": True},
            "permanent_address": {"required": False, "allow_null": True},
            "citizenship_number": {"required": False, "allow_null": True},
            "gender": {"required": False, "allow_null": True},
            "gender_other": {"required": False, "allow_null": True},
            "employment_type": {"required": False},
            "status": {"required": False},
            "remarks": {"required": False},
            "photo": {"required": False, "allow_null": True},
        }

    def validate(self, attrs):
        gender = attrs.get("gender", getattr(self.instance, "gender", None))
        if gender != "Other":
            attrs["gender_other"] = None

        candidate = self.instance or Employee()
        for field, value in attrs.items():
            setattr(candidate, field, value)
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return attrs


class EmployeeCreateSerializer(EmployeeWriteSerializer):
    """Complete personnel profile required for a new employee record.

    Database columns remain nullable for legacy imports, but new API-created
    records must contain the core government personnel profile.
    """

    father_name = serializers.CharField(max_length=100)
    grandfather_name = serializers.CharField(max_length=100)
    spouse_name = serializers.CharField(
        max_length=100,
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Optional; provide only when applicable.",
    )
    beneficiary_name = serializers.CharField(max_length=100)
    permanent_address = serializers.CharField(max_length=255)
    citizenship_number = serializers.CharField(max_length=50)
    gender = serializers.ChoiceField(choices=Employee._meta.get_field("gender").choices)
    phone_number = serializers.RegexField(
        r"^\+?[0-9]{7,15}$",
        help_text="Phone number containing 7-15 digits and optional + prefix.",
    )
    position = serializers.PrimaryKeyRelatedField(
        queryset=Position.objects.all(),
        help_text="Position ID from GET /api/positions/.",
    )
    level = serializers.PrimaryKeyRelatedField(
        queryset=Level.objects.all(),
        help_text="Level ID from GET /api/levels/.",
    )


class AttendanceRecordSerializer(serializers.ModelSerializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())

    class Meta:
        model = AttendanceRecord
        fields = (
            "id",
            "employee",
            "work_date",
            "check_in",
            "check_out",
            "status",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())
    approved_by = serializers.PrimaryKeyRelatedField(read_only=True)
    total_days = serializers.IntegerField(read_only=True)

    class Meta:
        model = LeaveRequest
        fields = (
            "id",
            "employee",
            "leave_type",
            "start_date",
            "end_date",
            "reason",
            "status",
            "approved_by",
            "approved_at",
            "remarks",
            "total_days",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "status", "approved_by", "approved_at", "created_at", "updated_at")


class LeaveApprovalSerializer(serializers.Serializer):
    remarks = serializers.CharField(required=False, allow_blank=True)


class ReportSummarySerializer(serializers.Serializer):
    employee_id = serializers.IntegerField(read_only=True)
    employee_name = serializers.CharField(read_only=True)
    period = serializers.DictField(read_only=True)
    attendance = serializers.DictField(read_only=True)
    leave_requests = serializers.DictField(read_only=True)


class OfficeTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfficeTransfer
        fields = "__all__"
        read_only_fields = (
            "initiated_by",
            "verified",
            "verified_by",
            "verified_on",
        )
