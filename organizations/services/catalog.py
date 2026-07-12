"""Transactional CRUD workflows for the organization catalog."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from organizations.exceptions import (
    ResourceConflictError,
    ResourceInUseError,
    ResourceNotFoundError,
    ResourceValidationError,
)
from organizations.repositories import (
    CategoryRepository,
    LevelRepository,
    OrganizationRepository,
    PositionRepository,
    ServiceRepository,
    SubCategoryRepository,
)


class _CatalogCrudService:
    """Shared transaction mechanics; concrete services declare domain ownership."""

    resource_name = "resource"
    repository_class = None
    soft_delete = False

    def __init__(self, *, repository=None):
        self.repository = repository or self.repository_class()

    def list_queryset(self):
        return self.repository.queryset()

    def get(self, resource_id):
        instance = self.repository.get_by_id(resource_id)
        if instance is None:
            raise ResourceNotFoundError(self.resource_name)
        return instance

    def create(self, *, data: dict, actor=None):
        try:
            with transaction.atomic():
                instance = self.repository.model(**data)
                self._assign_actor(instance, actor, creating=True)
                self._validate(instance)
                return self.repository.save(instance)
        except IntegrityError as exc:
            raise ResourceConflictError(self.resource_name) from exc

    def update(self, *, resource_id, data: dict, actor=None):
        try:
            with transaction.atomic():
                try:
                    instance = self.repository.get_for_update(resource_id)
                except self.repository.model.DoesNotExist as exc:
                    raise ResourceNotFoundError(self.resource_name) from exc

                for field, value in data.items():
                    setattr(instance, field, value)
                self._assign_actor(instance, actor, creating=False)
                self._validate(instance)
                return self.repository.save(instance)
        except IntegrityError as exc:
            raise ResourceConflictError(self.resource_name) from exc

    def delete(self, *, resource_id, actor=None):
        with transaction.atomic():
            try:
                instance = self.repository.get_for_update(resource_id)
            except self.repository.model.DoesNotExist as exc:
                raise ResourceNotFoundError(self.resource_name) from exc

            dependencies = self.repository.dependencies(instance)
            if dependencies:
                raise ResourceInUseError(self.resource_name, dependencies)

            if self.soft_delete:
                self.repository.soft_delete(instance, actor=actor)
            else:
                instance.delete()

    @staticmethod
    def _assign_actor(instance, actor, *, creating):
        if actor is None or not getattr(actor, "is_authenticated", False):
            return
        if hasattr(instance, "updated_by_id"):
            instance.updated_by = actor
        if creating and hasattr(instance, "created_by_id"):
            instance.created_by = actor

    @staticmethod
    def _validate(instance):
        try:
            instance.full_clean()
        except ValidationError as exc:
            details = (
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            )
            raise ResourceValidationError(details) from exc


class OrganizationService(_CatalogCrudService):
    resource_name = "organization"
    repository_class = OrganizationRepository
    soft_delete = True


class ServiceClassificationService(_CatalogCrudService):
    """CRUD for the civil-service `Service` classification model."""

    resource_name = "service"
    repository_class = ServiceRepository


class CategoryService(_CatalogCrudService):
    resource_name = "category"
    repository_class = CategoryRepository


class SubCategoryService(_CatalogCrudService):
    resource_name = "subcategory"
    repository_class = SubCategoryRepository


class LevelService(_CatalogCrudService):
    resource_name = "level"
    repository_class = LevelRepository


class PositionService(_CatalogCrudService):
    resource_name = "position"
    repository_class = PositionRepository
