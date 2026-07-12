from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from core.models import BigAutoSoftDeleteModel
from core.utils import Province


class Organization(BigAutoSoftDeleteModel):
    class UnitType(models.TextChoices):
        MINISTRY = "ministry", "Ministry / मन्त्रालय"
        DEPARTMENT = "department", "Department / विभाग"
        DIRECTORATE = "directorate", "Directorate / निर्देशनालय"
        DIVISION = "division", "Division / महाशाखा"
        BRANCH = "branch", "Branch / शाखा"
        SECTION = "section", "Section / उपशाखा"
        UNIT = "unit", "Unit / इकाई"
        OFFICE = "office", "Office / कार्यालय"

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=30, unique=True)
    org_type = models.CharField(max_length=30, choices=UnitType.choices)
    province = models.CharField(max_length=20, choices=Province.choices)
    address = models.TextField(blank=True, null=True)
    parent_org = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="child_orgs",
    )
    head_employee = models.ForeignKey(
        "employees.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="headed_organizations",
    )
    established_date_ad = models.DateField(blank=True, null=True)
    established_date_bs = models.CharField(max_length=10, blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    history = HistoricalRecords()

    class Meta(BigAutoSoftDeleteModel.Meta):
        indexes = [models.Index(fields=["parent_org", "is_active"])]

    def clean(self):
        super().clean()
        errors = {}
        if (
            self.head_employee_id
            and self.pk is not None
            and self.head_employee.working_organization_id != self.pk
        ):
            errors["head_employee"] = (
                "The organization head must be assigned to this organization."
            )
        if self.parent_org_id is None:
            if errors:
                raise ValidationError(errors)
            return
        if self.pk is not None and self.parent_org_id == self.pk:
            errors["parent_org"] = "An organization cannot parent itself."
        else:
            ancestor = self.parent_org
            visited = set()
            while ancestor is not None:
                if ancestor.pk == self.pk or ancestor.pk in visited:
                    errors["parent_org"] = (
                        "This parent would create an organization cycle."
                    )
                    break
                visited.add(ancestor.pk)
                ancestor = ancestor.parent_org
        if errors:
            raise ValidationError(errors)

    @property
    def headcount(self):
        if hasattr(self, "_active_headcount"):
            return self._active_headcount
        return self.employees.filter(status="IN_SERVICE").count()

    def __str__(self):
        return f"{self.name} ({self.get_org_type_display()})"


class Service(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Category(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="categories"
    )
    name = models.CharField(max_length=100)

    class Meta:
        unique_together = ("service", "name")

    def __str__(self):
        return f"{self.service.name} - {self.name}"


class SubCategory(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="subcategories"
    )
    name = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        unique_together = ("category", "name")

    def __str__(self):
        return (
            f"{self.category} - {self.name}"
            if self.name
            else f"{self.category} (No Subcategory)"
        )


class Level(models.Model):
    class GazettedType(models.TextChoices):
        GAZETTED_FIRST = "GAZETTED_FIRST", "Gazetted 1st"
        GAZETTED_SECOND = "GAZETTED_SECOND", "Gazetted 2nd"
        GAZETTED_THIRD = "GAZETTED_THIRD", "Gazetted 3rd"
        NON_GAZETTED = "NON_GAZETTED", "Non-Gazetted"

    name = models.CharField(max_length=50)  # e.g. "5th Level", "7th Level"
    gazetted_type = models.CharField(
        max_length=20, choices=GazettedType.choices, default=GazettedType.NON_GAZETTED
    )

    def __str__(self):
        return f"{self.name} ({self.get_gazetted_type_display()})"


class Position(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.SET_NULL, null=True, blank=True
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True
    )
    subcategory = models.ForeignKey(
        SubCategory, on_delete=models.SET_NULL, null=True, blank=True
    )
    level = models.ForeignKey(
        Level,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="positions",
    )
    title = models.CharField(max_length=100)

    class Meta:
        unique_together = ("service", "category", "subcategory", "title")

    def clean(self):
        super().clean()
        errors = {}
        if self.category_id:
            if not self.service_id:
                errors["service"] = "Service is required when category is selected."
            elif self.category.service_id != self.service_id:
                errors["category"] = (
                    "The selected category does not belong to the selected service."
                )
        if self.subcategory_id:
            if not self.category_id:
                errors["category"] = (
                    "Category is required when subcategory is selected."
                )
            elif self.subcategory.category_id != self.category_id:
                errors["subcategory"] = (
                    "The selected subcategory does not belong to the selected category."
                )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        parts = [
            self.service.name if self.service else "",
            self.category.name if self.category else "",
            self.subcategory.name if self.subcategory else "",
            self.title,
        ]
        return " > ".join(filter(None, parts))


class OrganizationPosition(models.Model):
    """A sanctioned position and its approved capacity in an organization."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="sanctioned_positions",
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.PROTECT,
        related_name="organization_assignments",
    )
    sanctioned_count = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "position"],
                name="unique_organization_position",
            ),
            models.CheckConstraint(
                condition=models.Q(sanctioned_count__gte=1),
                name="organization_position_count_gte_1",
            ),
        ]

    @property
    def filled_count(self):
        return self.organization.employees.filter(
            position=self.position,
            status="IN_SERVICE",
        ).count()

    def __str__(self):
        return f"{self.organization} - {self.position}"
