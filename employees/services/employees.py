"""Transactional employee CRUD and personnel-history workflows."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from employees.exceptions import (
    EmployeeConflictError,
    EmployeeInUseError,
    EmployeeNotFoundError,
    EmployeeValidationError,
)
from employees.repositories import EmployeeHistoryRepository, EmployeeRepository


class EmployeeService:
    def __init__(self, *, employee_repository=None, history_repository=None):
        self.employee_repository = employee_repository or EmployeeRepository()
        self.history_repository = history_repository or EmployeeHistoryRepository()

    def list_queryset(self):
        return self.employee_repository.queryset()

    def get(self, employee_id):
        employee = self.employee_repository.get_by_id(employee_id)
        if employee is None:
            raise EmployeeNotFoundError()
        return employee

    def create(self, *, data: dict, actor=None):
        try:
            with transaction.atomic():
                employee = self.employee_repository.model(**data)
                self._assign_actor(employee, actor, creating=True)
                self._validate(employee)
                employee._skip_employee_tracking = True
                self.employee_repository.save(employee)

                if employee.working_organization_id:
                    self.history_repository.create_transfer(
                        employee=employee,
                        to_organization=employee.working_organization,
                        status="RECRUITED",
                        actor=actor,
                        remarks="Initial appointment record",
                    )
                return employee
        except IntegrityError as exc:
            raise EmployeeConflictError() from exc

    def update(self, *, employee_id, data: dict, actor=None):
        try:
            with transaction.atomic():
                try:
                    employee = self.employee_repository.get_for_update(employee_id)
                except self.employee_repository.model.DoesNotExist as exc:
                    raise EmployeeNotFoundError() from exc

                old_organization_id = employee.working_organization_id
                old_status = employee.status
                for field, value in data.items():
                    setattr(employee, field, value)

                self._assign_actor(employee, actor, creating=False)
                self._validate(employee)
                employee._skip_employee_tracking = True
                self.employee_repository.save(employee)

                if (
                    employee.working_organization_id
                    and employee.working_organization_id != old_organization_id
                ):
                    self.history_repository.create_transfer(
                        employee=employee,
                        to_organization=employee.working_organization,
                        status="TRANSFERRED",
                        actor=actor,
                        remarks="Organization assignment changed",
                    )

                if employee.status != old_status:
                    self.history_repository.create_status_change(
                        employee=employee,
                        old_status=old_status,
                        new_status=employee.status,
                        remarks="Employee status changed",
                    )
                return employee
        except IntegrityError as exc:
            raise EmployeeConflictError() from exc

    def delete(self, *, employee_id, actor=None):
        with transaction.atomic():
            try:
                employee = self.employee_repository.get_for_update(employee_id)
            except self.employee_repository.model.DoesNotExist as exc:
                raise EmployeeNotFoundError() from exc

            dependencies = self.employee_repository.dependencies(employee)
            if dependencies:
                raise EmployeeInUseError(dependencies)
            self.employee_repository.soft_delete(employee, actor=actor)

    @staticmethod
    def _assign_actor(employee, actor, *, creating):
        if actor is None or not getattr(actor, "is_authenticated", False):
            return
        employee.initiated_by = actor
        employee.updated_by = actor
        if creating:
            employee.created_by = actor

    @staticmethod
    def _validate(employee):
        try:
            employee.full_clean()
        except ValidationError as exc:
            details = (
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            )
            raise EmployeeValidationError(details) from exc
