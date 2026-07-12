from django.contrib import admin

# Register your models here.
from .models import Employee, EmployeeContact, OfficeTransfer, ServiceBookEntry


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "ka_sa_num",
        "working_organization",
        "position",
        "status",
        "employment_type",
    )
    list_filter = ("working_organization", "status", "employment_type")
    search_fields = ("first_name", "last_name", "ka_sa_num")
    raw_id_fields = ("working_organization", "position", "level", "supervisor")


@admin.register(OfficeTransfer)
class OfficeTransferAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "to_organization",
        # "start_date_bs",
        # "end_date_bs",
    )
    list_filter = ("to_organization",)


@admin.register(EmployeeContact)
class EmployeeContactAdmin(admin.ModelAdmin):
    list_display = ("employee", "kind", "is_primary", "verified")
    list_filter = ("kind", "is_primary", "verified")
    raw_id_fields = ("employee",)


@admin.register(ServiceBookEntry)
class ServiceBookEntryAdmin(admin.ModelAdmin):
    list_display = ("employee", "entry_type", "effective_date", "order_reference")
    list_filter = ("entry_type", "effective_date")
    search_fields = ("employee__ka_sa_num", "order_reference")
    raw_id_fields = ("employee", "approved_by")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
