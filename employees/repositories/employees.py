"""ORM persistence boundary for employee workflows."""

from employees.models import Employee, EmployeeStatusHistory, OfficeTransfer


class EmployeeRepository:
    model = Employee

    def queryset(self):
        return self.model.objects.select_related(
            "working_organization",
            "position__service",
            "position__category",
            "position__subcategory",
            "level",
            "supervisor",
        )

    def get_by_id(self, employee_id):
        return self.queryset().filter(pk=employee_id).first()

    def get_for_update(self, employee_id):
        return self.model.objects.select_for_update().get(pk=employee_id)

    @staticmethod
    def save(employee):
        employee.save()
        return employee

    @staticmethod
    def dependencies(employee):
        checks = (
            ("organization head assignments", employee.headed_organizations.exists()),
            ("direct reports", employee.direct_reports.exists()),
        )
        return [name for name, exists in checks if exists]

    @staticmethod
    def soft_delete(employee, *, actor=None):
        employee.deleted_by = actor
        employee.delete()


class EmployeeHistoryRepository:
    @staticmethod
    def create_status_change(*, employee, old_status, new_status, remarks=""):
        return EmployeeStatusHistory.objects.create(
            employee=employee,
            old_status=old_status,
            new_status=new_status,
            remarks=remarks,
        )

    @staticmethod
    def create_transfer(
        *,
        employee,
        to_organization,
        status,
        actor=None,
        remarks="",
    ):
        return OfficeTransfer.objects.create(
            employee=employee,
            to_organization=to_organization,
            status=status,
            initiated_by=actor,
            remarks=remarks,
        )
