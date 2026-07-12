from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError

from employees.models import Employee

from .models import (
    Category,
    Level,
    Organization,
    OrganizationPosition,
    Position,
    Service,
    SubCategory,
)


class OrganizationReferenceSerializer(serializers.ModelSerializer):
    org_type_display = serializers.CharField(
        source="get_org_type_display", read_only=True
    )

    class Meta:
        model = Organization
        fields = ("id", "code", "name", "org_type", "org_type_display")


class EmployeeReferenceSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Employee
        fields = ("id", "ka_sa_num", "full_name")


class OrganizationReadSerializer(serializers.ModelSerializer):
    org_type_display = serializers.CharField(
        source="get_org_type_display", read_only=True
    )
    province_display = serializers.CharField(
        source="get_province_display", read_only=True
    )
    parent_org_id = serializers.IntegerField(read_only=True, allow_null=True)
    parent_org = OrganizationReferenceSerializer(read_only=True)
    head_employee_id = serializers.IntegerField(read_only=True, allow_null=True)
    head_employee = EmployeeReferenceSerializer(read_only=True)
    headcount = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organization
        fields = (
            "id",
            "name",
            "code",
            "org_type",
            "org_type_display",
            "province",
            "province_display",
            "address",
            "established_date_ad",
            "established_date_bs",
            "is_active",
            "parent_org_id",
            "parent_org",
            "head_employee_id",
            "head_employee",
            "headcount",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "row_version",
        )


class OrganizationWriteValidationMixin:
    def validate(self, attrs):
        candidate = self.instance or Organization()
        for field, value in attrs.items():
            setattr(candidate, field, value)
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return attrs


class OrganizationCreateSerializer(
    OrganizationWriteValidationMixin, serializers.ModelSerializer
):
    parent_org = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(),
        required=False,
        allow_null=True,
        help_text=(
            "Optional ID of an existing parent organization. Use "
            "GET /api/organizations/ to find valid IDs."
        ),
    )
    established_date_bs = serializers.RegexField(
        regex=r"^\d{4}-\d{2}-\d{2}$",
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=10,
        help_text="Optional Bikram Sambat date in YYYY-MM-DD format.",
    )

    class Meta:
        model = Organization
        fields = (
            "name",
            "code",
            "org_type",
            "province",
            "address",
            "established_date_ad",
            "established_date_bs",
            "is_active",
            "parent_org",
        )
        extra_kwargs = {
            "address": {"required": False, "allow_null": True},
            "established_date_ad": {"required": False, "allow_null": True},
            "is_active": {"required": False, "default": True},
            "org_type": {
                "help_text": "Select an organization type from the enum list."
            },
            "province": {
                "help_text": "Select a Nepal province from the enum list."
            },
        }

    def validate(self, attrs):
        if "head_employee" in self.initial_data:
            raise serializers.ValidationError(
                {
                    "head_employee": (
                        "Create the organization first, assign an employee to it, "
                        "then set the head with PATCH."
                    )
                }
            )
        return super().validate(attrs)


class OrganizationUpdateSerializer(OrganizationCreateSerializer):
    head_employee = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(),
        required=False,
        allow_null=True,
        help_text=(
            "Optional employee ID. The employee must already belong to this "
            "organization. Use GET /api/employees/?working_organization=<id>."
        ),
    )

    class Meta(OrganizationCreateSerializer.Meta):
        fields = OrganizationCreateSerializer.Meta.fields + ("head_employee",)

    def validate(self, attrs):
        return OrganizationWriteValidationMixin.validate(self, attrs)


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = "__all__"


class CategorySerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source="service.name", read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "service", "service_name"]


class SubCategorySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    service_name = serializers.CharField(source="category.service.name", read_only=True)

    class Meta:
        model = SubCategory
        fields = ["id", "name", "category", "category_name", "service_name"]


class LevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Level
        fields = "__all__"


class PositionSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source="service.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    subcategory_name = serializers.CharField(source="subcategory.name", read_only=True)

    class Meta:
        model = Position
        fields = [
            "id",
            "title",
            "service",
            "category",
            "subcategory",
            "level",
            "service_name",
            "category_name",
            "subcategory_name",
        ]

    def validate(self, attrs):
        relationship_fields = {"service", "category", "subcategory"}
        if self.instance is not None and relationship_fields.isdisjoint(attrs):
            return attrs

        service = self._effective_relation(attrs, "service")
        category = self._effective_relation(attrs, "category")
        subcategory = self._effective_relation(attrs, "subcategory")
        errors = {}

        if category is not None:
            if service is None:
                errors["service"] = "Service is required when category is selected."
            elif category.service_id != service.pk:
                errors["category"] = (
                    "The selected category does not belong to the selected service."
                )

        if subcategory is not None:
            if category is None:
                errors["category"] = (
                    "Category is required when subcategory is selected."
                )
            elif subcategory.category_id != category.pk:
                errors["subcategory"] = (
                    "The selected subcategory does not belong to the selected category."
                )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def _effective_relation(self, attrs, field_name):
        if field_name in attrs:
            return attrs[field_name]
        if self.instance is not None:
            return getattr(self.instance, field_name)
        return None


class OrganizationPositionSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )
    position_title = serializers.CharField(source="position.title", read_only=True)
    filled_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = OrganizationPosition
        fields = (
            "id",
            "organization",
            "organization_name",
            "position",
            "position_title",
            "sanctioned_count",
            "filled_count",
            "is_active",
        )
