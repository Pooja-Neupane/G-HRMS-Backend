import django_filters
from .models import Employee


class EmployeeFilter(django_filters.FilterSet):
    # allows filtering by organization name (case-insensitive match)
    working_organization_name = django_filters.CharFilter(
        field_name="working_organization__name", lookup_expr="icontains"
    )

    # allows filtering by service category name
    service_category_name = django_filters.CharFilter(
        field_name="position__category__name", lookup_expr="icontains"
    )

    position_name = django_filters.CharFilter(
        field_name="position__title", lookup_expr="icontains"
    )

    # optional: filter by join date range
    join_date_after = django_filters.DateFilter(
        field_name="jobstartdate_ad", lookup_expr="gte"
    )
    join_date_before = django_filters.DateFilter(
        field_name="jobstartdate_ad", lookup_expr="lte"
    )

    class Meta:
        model = Employee
        fields = [
            "first_name",
            "status",  # e.g. in_service, retired
            "ka_sa_num",
            "level",  # numeric or enum level
            "working_organization",  # still supports ID-based filtering
            "working_organization_name",  # new text-based filtering
            "service_category_name",  # new text-based filtering
        ]
