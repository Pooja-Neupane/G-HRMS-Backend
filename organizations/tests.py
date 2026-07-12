from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from drf_spectacular.generators import SchemaGenerator

from employees.models import Employee
from organizations.exceptions import ResourceValidationError
from organizations.models import (
    Category,
    Level,
    Organization,
    Position,
    Service,
    SubCategory,
)
from organizations.serializers import OrganizationUpdateSerializer, PositionSerializer
from organizations.services import OrganizationService, PositionService


User = get_user_model()


class PositionSerializerValidationTests(TestCase):
    def setUp(self):
        self.administration = Service.objects.create(name="Administration")
        self.engineering = Service.objects.create(name="Engineering")
        self.revenue = Category.objects.create(
            service=self.administration,
            name="Revenue",
        )
        self.general_admin = Category.objects.create(
            service=self.administration,
            name="General Administration",
        )
        self.tax = SubCategory.objects.create(
            category=self.revenue,
            name="Tax",
        )
        self.personnel = SubCategory.objects.create(
            category=self.general_admin,
            name="Personnel",
        )
        self.position = Position.objects.create(
            title="Revenue Officer",
            service=self.administration,
            category=self.revenue,
            subcategory=self.tax,
        )

    def test_accepts_consistent_taxonomy_chain(self):
        serializer = PositionSerializer(
            data={
                "title": "Senior Revenue Officer",
                "service": self.administration.pk,
                "category": self.revenue.pk,
                "subcategory": self.tax.pk,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_allows_position_without_optional_taxonomy(self):
        serializer = PositionSerializer(data={"title": "Special Officer"})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_rejects_category_without_service(self):
        serializer = PositionSerializer(
            data={"title": "Revenue Officer", "category": self.revenue.pk}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("service", serializer.errors)

    def test_rejects_category_from_another_service(self):
        serializer = PositionSerializer(
            data={
                "title": "Invalid Officer",
                "service": self.engineering.pk,
                "category": self.revenue.pk,
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("category", serializer.errors)

    def test_rejects_subcategory_from_another_category(self):
        serializer = PositionSerializer(
            data={
                "title": "Invalid Officer",
                "service": self.administration.pk,
                "category": self.revenue.pk,
                "subcategory": self.personnel.pk,
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("subcategory", serializer.errors)

    def test_partial_service_change_validates_existing_category(self):
        serializer = PositionSerializer(
            self.position,
            data={"service": self.engineering.pk},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("category", serializer.errors)

    def test_partial_category_change_validates_existing_subcategory(self):
        serializer = PositionSerializer(
            self.position,
            data={"category": self.general_admin.pk},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("subcategory", serializer.errors)

    def test_title_only_partial_update_remains_valid(self):
        serializer = PositionSerializer(
            self.position,
            data={"title": "Chief Revenue Officer"},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)


class OrganizationHierarchyTests(TestCase):
    def setUp(self):
        self.ministry = Organization.objects.create(
            name="Ministry",
            code="ORG-001",
            org_type=Organization.UnitType.MINISTRY,
            province="03",
        )
        self.department = Organization.objects.create(
            name="Department",
            code="ORG-002",
            org_type=Organization.UnitType.DEPARTMENT,
            province="03",
            parent_org=self.ministry,
        )

    def test_rejects_hierarchy_cycle(self):
        serializer = OrganizationUpdateSerializer(
            self.ministry,
            data={"parent_org": self.department.pk},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("parent_org", serializer.errors)

    def test_soft_delete_hides_organization(self):
        organization_id = self.department.pk
        self.department.delete()
        self.assertFalse(Organization.objects.filter(pk=organization_id).exists())
        self.assertTrue(Organization.all_objects.filter(pk=organization_id).exists())

    def test_branch_has_bilingual_label_and_can_be_nested(self):
        branch = Organization.objects.create(
            name="Personnel Administration Branch",
            code="ORG-BRANCH-001",
            org_type=Organization.UnitType.BRANCH,
            province="03",
            parent_org=self.department,
        )

        self.assertEqual(branch.get_org_type_display(), "Branch / शाखा")
        self.assertEqual(branch.parent_org, self.department)


class OrganizationCatalogServiceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="catalog-admin",
            email="catalog-admin@example.com",
            password="StrongPassword@123",
            role=User.Role.SUPERADMIN,
            status=User.Status.ACTIVE,
            is_superuser=True,
        )

    def test_organization_create_assigns_audit_actor_and_soft_delete_actor(self):
        service = OrganizationService()
        organization = service.create(
            data={
                "name": "Test Ministry",
                "code": "TEST-MIN",
                "org_type": Organization.UnitType.MINISTRY,
                "province": "03",
            },
            actor=self.admin,
        )

        self.assertEqual(organization.created_by, self.admin)
        self.assertEqual(organization.updated_by, self.admin)

        service.delete(resource_id=organization.pk, actor=self.admin)
        deleted = Organization.all_objects.get(pk=organization.pk)
        self.assertTrue(deleted.is_deleted)
        self.assertEqual(deleted.deleted_by, self.admin)

    def test_position_service_rejects_inconsistent_taxonomy(self):
        administration = Service.objects.create(name="Administration")
        engineering = Service.objects.create(name="Engineering")
        category = Category.objects.create(
            service=administration,
            name="General Administration",
        )

        with self.assertRaises(ResourceValidationError):
            PositionService().create(
                data={
                    "title": "Invalid Position",
                    "service": engineering,
                    "category": category,
                },
                actor=self.admin,
            )


class OrganizationCatalogApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="organization-admin",
            email="organization-admin@example.com",
            password="StrongPassword@123",
            role=User.Role.SUPERADMIN,
            status=User.Status.ACTIVE,
            is_superuser=True,
        )
        self.viewer = User.objects.create_user(
            username="organization-viewer",
            email="organization-viewer@example.com",
            password="StrongPassword@123",
            role=User.Role.VIEWER,
            status=User.Status.ACTIVE,
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_reads_require_authentication_and_allow_authenticated_viewer(self):
        response = self.client.get(reverse("organization-list"))
        self.assertEqual(response.status_code, 401)

        self.authenticate(self.viewer)
        response = self.client.get(reverse("organization-list"))
        self.assertEqual(response.status_code, 200)

    def test_mutations_require_superadmin(self):
        self.authenticate(self.viewer)
        response = self.client.post(
            reverse("service-list"),
            {"name": "Administration"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_complete_catalog_crud_lifecycle(self):
        self.authenticate(self.admin)

        organization = self.client.post(
            reverse("organization-list"),
            {
                "name": "Ministry of Test Affairs",
                "code": "MTA",
                "org_type": Organization.UnitType.MINISTRY,
                "province": "03",
            },
            format="json",
        )
        self.assertEqual(organization.status_code, 201, organization.data)
        organization_id = organization.data["id"]
        self.assertIsNone(organization.data["parent_org"])
        self.assertIsNone(organization.data["parent_org_id"])
        self.assertIsNone(organization.data["head_employee"])
        self.assertIsNone(organization.data["head_employee_id"])
        self.assertNotIn("is_deleted", organization.data)

        civil_service = self.client.post(
            reverse("service-list"),
            {"name": "Administration"},
            format="json",
        )
        self.assertEqual(civil_service.status_code, 201, civil_service.data)
        service_id = civil_service.data["id"]

        category = self.client.post(
            reverse("category-list"),
            {"name": "General Administration", "service": service_id},
            format="json",
        )
        self.assertEqual(category.status_code, 201, category.data)
        category_id = category.data["id"]

        subcategory = self.client.post(
            reverse("subcategory-list"),
            {"name": "Personnel", "category": category_id},
            format="json",
        )
        self.assertEqual(subcategory.status_code, 201, subcategory.data)
        subcategory_id = subcategory.data["id"]

        level = self.client.post(
            reverse("level-list"),
            {"name": "Seventh Level", "gazetted_type": "NON_GAZETTED"},
            format="json",
        )
        self.assertEqual(level.status_code, 201, level.data)
        level_id = level.data["id"]

        position = self.client.post(
            reverse("position-list"),
            {
                "title": "Personnel Officer",
                "service": service_id,
                "category": category_id,
                "subcategory": subcategory_id,
                "level": level_id,
            },
            format="json",
        )
        self.assertEqual(position.status_code, 201, position.data)
        position_id = position.data["id"]

        updated = self.client.patch(
            reverse("category-detail", kwargs={"pk": category_id}),
            {"name": "General Administration and HR"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["name"], "General Administration and HR")

        listed = self.client.get(
            reverse("position-list"),
            {"service": service_id, "search": "Personnel"},
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["count"], 1)

        delete_order = (
            ("position-detail", position_id),
            ("subcategory-detail", subcategory_id),
            ("category-detail", category_id),
            ("service-detail", service_id),
            ("level-detail", level_id),
            ("organization-detail", organization_id),
        )
        for route_name, resource_id in delete_order:
            response = self.client.delete(
                reverse(route_name, kwargs={"pk": resource_id})
            )
            self.assertEqual(response.status_code, 204, response.data)

        self.assertFalse(Organization.objects.filter(pk=organization_id).exists())
        self.assertTrue(
            Organization.all_objects.filter(pk=organization_id).exists()
        )

    def test_delete_rejects_dependent_taxonomy(self):
        self.authenticate(self.admin)
        civil_service = Service.objects.create(name="Engineering")
        Category.objects.create(service=civil_service, name="Civil")

        response = self.client.delete(
            reverse("service-detail", kwargs={"pk": civil_service.pk})
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"]["code"], "resource_in_use")
        self.assertIn("categories", response.data["error"]["details"]["dependencies"])

    def test_create_rejects_head_employee_and_patch_accepts_assigned_employee(self):
        self.authenticate(self.admin)
        rejected = self.client.post(
            reverse("organization-list"),
            {
                "name": "Invalid Head Ministry",
                "code": "IHM",
                "org_type": Organization.UnitType.MINISTRY,
                "province": "03",
                "head_employee": 123,
            },
            format="json",
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("head_employee", rejected.data["error"]["details"])

        organization = Organization.objects.create(
            name="Head Assignment Ministry",
            code="HAM",
            org_type=Organization.UnitType.MINISTRY,
            province="03",
        )
        employee = Employee.objects.create(
            first_name="Sita",
            last_name="Shrestha",
            ka_sa_num="EMP-HEAD-001",
            dob_bs="2050-01-01",
            dob_ad=date(1993, 4, 14),
            jobstartdate_bs="2080-01-01",
            jobstartdate_ad=date(2023, 4, 14),
            current_position_date_bs="2080-01-01",
            current_position_date_ad=date(2023, 4, 14),
            email="sita.head@example.com",
            working_organization=organization,
        )

        response = self.client.patch(
            reverse("organization-detail", kwargs={"pk": organization.pk}),
            {"head_employee": employee.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["head_employee_id"], employee.pk)
        self.assertEqual(response.data["head_employee"]["full_name"], "Sita Shrestha")

    def test_position_create_rejects_inconsistent_hierarchy(self):
        self.authenticate(self.admin)
        administration = Service.objects.create(name="Administration")
        engineering = Service.objects.create(name="Engineering")
        category = Category.objects.create(
            service=administration,
            name="Revenue",
        )

        response = self.client.post(
            reverse("position-list"),
            {
                "title": "Invalid Officer",
                "service": engineering.pk,
                "category": category.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("category", response.data["error"]["details"])

    def test_unknown_resource_uses_application_error_contract(self):
        self.authenticate(self.admin)
        response = self.client.get(reverse("level-detail", kwargs={"pk": 999999}))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"]["code"], "level_not_found")


class OrganizationOpenApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.schema = SchemaGenerator().get_schema(request=None, public=True)

    def test_create_schema_uses_choices_and_excludes_head_employee(self):
        create_schema = self.schema["components"]["schemas"][
            "OrganizationCreateRequest"
        ]
        properties = create_schema["properties"]

        self.assertNotIn("head_employee", properties)
        self.assertTrue(properties["parent_org"]["nullable"])
        self.assertEqual(
            self.schema["components"]["schemas"]["OrgTypeEnum"]["enum"],
            [
                "ministry",
                "department",
                "directorate",
                "division",
                "branch",
                "section",
                "unit",
                "office",
            ],
        )
        self.assertEqual(
            self.schema["components"]["schemas"]["ProvinceEnum"]["enum"],
            ["01", "02", "03", "04", "05", "06", "07"],
        )

    def test_catalog_resources_have_separate_tags(self):
        expected_tags = {
            "/api/organizations/": "Organizations",
            "/api/services/": "Services",
            "/api/categories/": "Categories",
            "/api/subcategories/": "Subcategories",
            "/api/levels/": "Levels",
            "/api/positions/": "Positions",
        }
        for path, tag in expected_tags.items():
            self.assertEqual(self.schema["paths"][path]["get"]["tags"], [tag])
