"""Transactional CRUD and submit workflow for logical employee documents."""

import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from documents.exceptions import (
    DocumentConflictError,
    DocumentNotFoundError,
    DocumentValidationError,
)
from documents.repositories import EmployeeDocumentRepository
from documents.services.uploads import DocumentUploadService


class EmployeeDocumentService:
    # Metadata an upsert may refresh on an existing single-instance document.
    EDITABLE_METADATA_FIELDS = (
        "title",
        "document_number",
        "issued_by",
        "issue_date_ad",
        "issue_date_bs",
        "expiry_date_ad",
        "expiry_date_bs",
        "remarks",
    )

    def __init__(self, *, repository=None, upload_service=None):
        self.repository = repository or EmployeeDocumentRepository()
        self.upload_service = upload_service or DocumentUploadService()

    def list_queryset(self):
        return self.repository.queryset()

    def get(self, document_id):
        instance = self.repository.get_by_id(document_id)
        if instance is None:
            raise DocumentNotFoundError()
        return instance

    def create(self, *, data, actor=None):
        try:
            with transaction.atomic():
                return self._build_and_save(data, actor)
        except IntegrityError as exc:
            raise DocumentConflictError() from exc

    def submit(self, *, data, actor=None, upload_source):
        """Create-or-append in one step: the API's primary upload action.

        For a single-instance category (allow_multiple=False) an existing active
        document is reused — its editable metadata is refreshed and a new file
        version is appended (the "replace" case). Otherwise a new document with
        an auto-generated code is created. Returns the document with its now-
        current version.
        """
        data = dict(data)
        uploaded_file = data.pop("file")
        employee = data["employee"]
        category = data["category"]

        try:
            with transaction.atomic():
                existing = (
                    self.repository.get_active_for_category_for_update(
                        employee_id=employee.id, category_id=category.id
                    )
                )
                if existing is not None and not category.allow_multiple:
                    document = existing
                    for field in self.EDITABLE_METADATA_FIELDS:
                        if field in data:
                            setattr(document, field, data[field])
                    self._assign_actor(document, actor, creating=False)
                    self._validate(document)
                    self.repository.save(document)
                else:
                    data["code"] = self._generate_code()
                    document = self._build_and_save(data, actor)

                self.upload_service.upload_new_version(
                    document_id=document.id,
                    uploaded_file=uploaded_file,
                    upload_source=upload_source,
                    actor=actor,
                )
        except IntegrityError as exc:
            raise DocumentConflictError() from exc

        return self.repository.get_by_id(document.id)

    def update(self, *, document_id, data, actor=None):
        try:
            with transaction.atomic():
                try:
                    instance = self.repository.get_for_update(document_id)
                except self.repository.model.DoesNotExist as exc:
                    raise DocumentNotFoundError() from exc

                for field, value in data.items():
                    setattr(instance, field, value)
                self._assign_actor(instance, actor, creating=False)
                self._validate(instance)
                return self.repository.save(instance)
        except IntegrityError as exc:
            raise DocumentConflictError() from exc

    def delete(self, *, document_id, actor=None):
        with transaction.atomic():
            try:
                instance = self.repository.get_for_update(document_id)
            except self.repository.model.DoesNotExist as exc:
                raise DocumentNotFoundError() from exc

            if actor is not None and getattr(actor, "is_authenticated", False):
                instance.deleted_by = actor
            instance.delete()

    def _build_and_save(self, data, actor):
        instance = self.repository.model(**data)
        self._assign_actor(instance, actor, creating=True)
        self._validate(instance)
        return self.repository.save(instance)

    @staticmethod
    def _generate_code():
        return f"DOC-{uuid.uuid4().hex[:12].upper()}"

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
            raise DocumentValidationError(details) from exc
