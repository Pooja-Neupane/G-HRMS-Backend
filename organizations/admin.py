from django.contrib import admin
from .models import Level, Organization, OrganizationPosition, Position


# Register your models here.
@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "org_type", "province", "is_active")
    search_fields = ("name", "code")
    list_filter = ("org_type", "province", "is_active")
    ordering = ("name",)
    date_hierarchy = "established_date_ad"
    raw_id_fields = ("parent_org", "head_employee")


@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ("name", "gazetted_type")
    list_filter = ("gazetted_type",)


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("title", "service", "category", "subcategory", "level")
    list_filter = ("service", "category", "level")
    search_fields = ("title",)


@admin.register(OrganizationPosition)
class OrganizationPositionAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "position",
        "sanctioned_count",
        "filled_count",
        "is_active",
    )
    list_filter = ("is_active", "organization")
    raw_id_fields = ("organization", "position")
