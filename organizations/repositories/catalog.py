"""ORM persistence boundaries for organizations and civil-service taxonomy."""

from django.db.models import Count, Q

from organizations.models import (
    Category,
    Level,
    Organization,
    Position,
    Service,
    SubCategory,
)


class OrganizationRepository:
    model = Organization

    def queryset(self):
        return self.model.objects.select_related(
            "parent_org", "head_employee"
        ).annotate(
            _active_headcount=Count(
                "employees",
                filter=Q(
                    employees__status="IN_SERVICE",
                    employees__is_deleted=False,
                ),
            )
        )

    def get_by_id(self, organization_id):
        return self.queryset().filter(pk=organization_id).first()

    def get_for_update(self, organization_id):
        return self.model.objects.select_for_update().get(pk=organization_id)

    @staticmethod
    def save(organization):
        organization.save()
        return organization

    @staticmethod
    def dependencies(organization):
        checks = (
            ("child organizations", organization.child_orgs.exists()),
            ("employees", organization.employees.exists()),
            ("user accounts", organization.users.exists()),
            ("sanctioned positions", organization.sanctioned_positions.exists()),
            ("office transfers", organization.transfers_to.exists()),
        )
        return [name for name, exists in checks if exists]

    @staticmethod
    def soft_delete(organization, *, actor=None):
        organization.deleted_by = actor
        organization.delete()


class ServiceRepository:
    model = Service

    def queryset(self):
        return self.model.objects.all()

    def get_by_id(self, service_id):
        return self.queryset().filter(pk=service_id).first()

    def get_for_update(self, service_id):
        return self.model.objects.select_for_update().get(pk=service_id)

    @staticmethod
    def save(service):
        service.save()
        return service

    @staticmethod
    def dependencies(service):
        checks = (
            ("categories", service.categories.exists()),
            ("positions", service.position_set.exists()),
        )
        return [name for name, exists in checks if exists]


class CategoryRepository:
    model = Category

    def queryset(self):
        return self.model.objects.select_related("service")

    def get_by_id(self, category_id):
        return self.queryset().filter(pk=category_id).first()

    def get_for_update(self, category_id):
        return self.model.objects.select_for_update().get(pk=category_id)

    @staticmethod
    def save(category):
        category.save()
        return category

    @staticmethod
    def dependencies(category):
        checks = (
            ("subcategories", category.subcategories.exists()),
            ("positions", category.position_set.exists()),
        )
        return [name for name, exists in checks if exists]


class SubCategoryRepository:
    model = SubCategory

    def queryset(self):
        return self.model.objects.select_related("category__service")

    def get_by_id(self, subcategory_id):
        return self.queryset().filter(pk=subcategory_id).first()

    def get_for_update(self, subcategory_id):
        return self.model.objects.select_for_update().get(pk=subcategory_id)

    @staticmethod
    def save(subcategory):
        subcategory.save()
        return subcategory

    @staticmethod
    def dependencies(subcategory):
        return ["positions"] if subcategory.position_set.exists() else []


class LevelRepository:
    model = Level

    def queryset(self):
        return self.model.objects.all()

    def get_by_id(self, level_id):
        return self.queryset().filter(pk=level_id).first()

    def get_for_update(self, level_id):
        return self.model.objects.select_for_update().get(pk=level_id)

    @staticmethod
    def save(level):
        level.save()
        return level

    @staticmethod
    def dependencies(level):
        checks = (
            ("positions", level.positions.exists()),
            ("employees", level.employees.exists()),
        )
        return [name for name, exists in checks if exists]


class PositionRepository:
    model = Position

    def queryset(self):
        return self.model.objects.select_related(
            "service",
            "category__service",
            "subcategory__category",
            "level",
        )

    def get_by_id(self, position_id):
        return self.queryset().filter(pk=position_id).first()

    def get_for_update(self, position_id):
        return self.model.objects.select_for_update().get(pk=position_id)

    @staticmethod
    def save(position):
        position.save()
        return position

    @staticmethod
    def dependencies(position):
        checks = (
            ("employees", position.employees.exists()),
            ("sanctioned positions", position.organization_assignments.exists()),
        )
        return [name for name, exists in checks if exists]
