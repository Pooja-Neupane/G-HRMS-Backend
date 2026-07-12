from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from account.models import RefreshToken
from authentication.services.access_tokens import PasetoAccessTokenService


User = get_user_model()

LIST_URL = "authentication:admin-user-list"
DETAIL_URL = "authentication:admin-user-detail"
STATUS_URL = "authentication:admin-user-status"


class UserAdminApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tokens = PasetoAccessTokenService()

        self.admin = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="StrongPassword@123",
            role=User.Role.SUPERADMIN,
            status=User.Status.ACTIVE,
            is_superuser=True,
            is_staff=True,
        )
        self.viewer = User.objects.create_user(
            username="viewer",
            email="viewer@example.com",
            password="StrongPassword@123",
            role=User.Role.VIEWER,
            status=User.Status.ACTIVE,
        )
        self.invited = User.objects.create_user(
            username="invitee",
            email="invitee@example.com",
            password="StrongPassword@123",
            status=User.Status.INVITED,
        )

    def auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.tokens.issue(user=user)}"}

    def detail(self, user):
        return reverse(DETAIL_URL, kwargs={"pk": user.pk})

    def status_url(self, user):
        return reverse(STATUS_URL, kwargs={"pk": user.pk})

    # ----- permissions ---------------------------------------------------

    def test_list_requires_authentication(self):
        self.assertEqual(self.client.get(reverse(LIST_URL)).status_code, 401)

    def test_list_forbidden_for_non_admin(self):
        response = self.client.get(reverse(LIST_URL), **self.auth(self.viewer))
        self.assertEqual(response.status_code, 403)

    def test_create_forbidden_for_non_admin(self):
        response = self.client.post(
            reverse(LIST_URL),
            {
                "username": "x",
                "email": "x@example.com",
                "password": "StrongPassword@123",
                "role": User.Role.VIEWER,
            },
            format="json",
            **self.auth(self.viewer),
        )
        self.assertEqual(response.status_code, 403)

    # ----- read ----------------------------------------------------------

    def test_superadmin_lists_users(self):
        response = self.client.get(reverse(LIST_URL), **self.auth(self.admin))
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)
        self.assertGreaterEqual(response.data["count"], 3)

    def test_list_filter_by_status(self):
        response = self.client.get(
            reverse(LIST_URL), {"status": "invited"}, **self.auth(self.admin)
        )
        self.assertEqual(response.status_code, 200)
        emails = {row["email"] for row in response.data["results"]}
        self.assertIn("invitee@example.com", emails)
        self.assertNotIn("admin@example.com", emails)

    def test_retrieve_user(self):
        response = self.client.get(
            self.detail(self.viewer), **self.auth(self.admin)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], "viewer@example.com")

    # ----- create --------------------------------------------------------

    def test_create_active_user(self):
        response = self.client.post(
            reverse(LIST_URL),
            {
                "username": "newhire",
                "email": "newhire@example.com",
                "password": "StrongPassword@123",
                "role": User.Role.HR_PERSONNEL,
                "first_name": "New",
                "last_name": "Hire",
            },
            format="json",
            **self.auth(self.admin),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], User.Status.ACTIVE)
        self.assertEqual(response.data["role"], User.Role.HR_PERSONNEL)

        user = User.objects.get(username="newhire")
        self.assertTrue(user.is_active)
        self.assertEqual(user.status, User.Status.ACTIVE)
        self.assertTrue(user.check_password("StrongPassword@123"))

    def test_create_rejects_duplicate_username(self):
        response = self.client.post(
            reverse(LIST_URL),
            {
                "username": "viewer",
                "email": "fresh@example.com",
                "password": "StrongPassword@123",
                "role": User.Role.VIEWER,
            },
            format="json",
            **self.auth(self.admin),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.data["error"]["details"])

    def test_create_rejects_weak_password(self):
        response = self.client.post(
            reverse(LIST_URL),
            {
                "username": "weak",
                "email": "weak@example.com",
                "password": "123",
                "role": User.Role.VIEWER,
            },
            format="json",
            **self.auth(self.admin),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data["error"]["details"])

    # ----- update --------------------------------------------------------

    def test_update_role(self):
        response = self.client.patch(
            self.detail(self.viewer),
            {"role": User.Role.HR_PERSONNEL},
            format="json",
            **self.auth(self.admin),
        )
        self.assertEqual(response.status_code, 200)
        self.viewer.refresh_from_db()
        self.assertEqual(self.viewer.role, User.Role.HR_PERSONNEL)

    # ----- soft delete ---------------------------------------------------

    def test_soft_delete_deactivates_and_revokes_sessions(self):
        token = RefreshToken.objects.create(
            user=self.viewer,
            token_hash="hash-del",
            expires_at=timezone.now() + timedelta(days=7),
        )

        response = self.client.delete(
            self.detail(self.viewer), **self.auth(self.admin)
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], User.Status.SUSPENDED)
        self.viewer.refresh_from_db()
        token.refresh_from_db()
        self.assertFalse(self.viewer.is_active)
        self.assertTrue(token.is_revoked)

    def test_cannot_deactivate_self(self):
        response = self.client.delete(
            self.detail(self.admin), **self.auth(self.admin)
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["error"]["code"], "self_status_change_forbidden"
        )

    # ----- status action -------------------------------------------------

    def test_status_requires_authentication(self):
        response = self.client.patch(
            self.status_url(self.invited), {"status": "active"}, format="json"
        )
        self.assertEqual(response.status_code, 401)

    def test_status_forbidden_for_non_admin(self):
        response = self.client.patch(
            self.status_url(self.invited),
            {"status": "active"},
            format="json",
            **self.auth(self.viewer),
        )
        self.assertEqual(response.status_code, 403)

    def test_superadmin_activates_invited_user(self):
        response = self.client.patch(
            self.status_url(self.invited),
            {"status": "active"},
            format="json",
            **self.auth(self.admin),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], User.Status.ACTIVE)
        self.invited.refresh_from_db()
        self.assertEqual(self.invited.status, User.Status.ACTIVE)
        self.assertTrue(self.invited.is_active)

    def test_status_invalid_value_is_rejected(self):
        response = self.client.patch(
            self.status_url(self.invited),
            {"status": "invited"},
            format="json",
            **self.auth(self.admin),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "validation_error")

    def test_status_redundant_activation_conflicts(self):
        response = self.client.patch(
            self.status_url(self.viewer),
            {"status": "active"},
            format="json",
            **self.auth(self.admin),
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data["error"]["code"], "invalid_status_transition"
        )
