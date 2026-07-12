from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from account.models import RefreshToken
from authentication.exceptions import (
    InvalidStatusTransitionError,
    SelfStatusChangeError,
    UserNotFoundError,
)
from authentication.services import UserAdminService


User = get_user_model()


class UserAdminServiceTests(TestCase):
    def setUp(self):
        self.service = UserAdminService()
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="StrongPassword@123",
            role=User.Role.SUPERADMIN,
            status=User.Status.ACTIVE,
            is_superuser=True,
            is_staff=True,
        )
        self.invited = User.objects.create_user(
            username="invitee",
            email="invitee@example.com",
            password="StrongPassword@123",
            status=User.Status.INVITED,
        )

    def test_create_user_is_active_with_usable_password(self):
        user = self.service.create_user(
            username="provisioned",
            email="Provisioned@Example.com",
            password="StrongPassword@123",
            role=User.Role.HR_PERSONNEL,
            actor=self.admin,
        )

        user.refresh_from_db()
        self.assertEqual(user.status, User.Status.ACTIVE)
        self.assertTrue(user.is_active)
        self.assertEqual(user.role, User.Role.HR_PERSONNEL)
        self.assertTrue(user.check_password("StrongPassword@123"))

    def test_update_user_changes_allowed_fields(self):
        user = self.service.update_user(
            user_id=self.invited.pk,
            data={"role": User.Role.KITABKHANA, "first_name": "Indra"},
            actor=self.admin,
        )

        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.KITABKHANA)
        self.assertEqual(user.first_name, "Indra")

    def test_deactivate_user_soft_deletes_and_revokes(self):
        active = User.objects.create_user(
            username="leaver",
            email="leaver@example.com",
            password="StrongPassword@123",
            status=User.Status.ACTIVE,
        )
        token = RefreshToken.objects.create(
            user=active,
            token_hash="hash-soft",
            expires_at=timezone.now() + timedelta(days=7),
        )

        user = self.service.deactivate_user(
            user_id=active.pk, actor=self.admin
        )

        token.refresh_from_db()
        self.assertEqual(user.status, User.Status.SUSPENDED)
        self.assertFalse(user.is_active)
        self.assertTrue(token.is_revoked)

    def test_cannot_deactivate_self(self):
        with self.assertRaises(SelfStatusChangeError):
            self.service.deactivate_user(
                user_id=self.admin.pk, actor=self.admin
            )

    def test_activate_invited_user_clears_lockout(self):
        self.invited.failed_login_count = 4
        self.invited.locked_until = timezone.now() + timedelta(minutes=5)
        self.invited.save(update_fields=["failed_login_count", "locked_until"])

        user = self.service.set_status(
            user_id=self.invited.pk,
            new_status=User.Status.ACTIVE,
            actor=self.admin,
        )

        self.assertEqual(user.status, User.Status.ACTIVE)
        self.assertEqual(user.failed_login_count, 0)
        self.assertIsNone(user.locked_until)

    def test_suspend_active_user_revokes_sessions(self):
        active = User.objects.create_user(
            username="worker",
            email="worker@example.com",
            password="StrongPassword@123",
            status=User.Status.ACTIVE,
        )
        token = RefreshToken.objects.create(
            user=active,
            token_hash="hash-1",
            expires_at=timezone.now() + timedelta(days=7),
        )

        user = self.service.set_status(
            user_id=active.pk,
            new_status=User.Status.SUSPENDED,
            actor=self.admin,
        )

        token.refresh_from_db()
        self.assertEqual(user.status, User.Status.SUSPENDED)
        self.assertTrue(token.is_revoked)

    def test_reactivate_suspended_user(self):
        self.invited.status = User.Status.SUSPENDED
        self.invited.save(update_fields=["status"])

        user = self.service.set_status(
            user_id=self.invited.pk,
            new_status=User.Status.ACTIVE,
            actor=self.admin,
        )

        self.assertEqual(user.status, User.Status.ACTIVE)

    def test_invalid_transition_is_rejected(self):
        active = User.objects.create_user(
            username="already",
            email="already@example.com",
            password="StrongPassword@123",
            status=User.Status.ACTIVE,
        )

        with self.assertRaises(InvalidStatusTransitionError):
            self.service.set_status(
                user_id=active.pk,
                new_status=User.Status.ACTIVE,
                actor=self.admin,
            )

    def test_unknown_user_is_rejected(self):
        with self.assertRaises(UserNotFoundError):
            self.service.set_status(
                user_id=999999,
                new_status=User.Status.ACTIVE,
                actor=self.admin,
            )

    def test_cannot_change_own_status(self):
        with self.assertRaises(SelfStatusChangeError):
            self.service.set_status(
                user_id=self.admin.pk,
                new_status=User.Status.SUSPENDED,
                actor=self.admin,
            )
