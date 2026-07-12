from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from account.models import AuthEvent
from authentication.exceptions import (
    AccountInactiveError,
    AccountLockedError,
    InvalidCredentialsError,
)
from authentication.services import AuthenticationService
from authentication.services import RevokedRefreshToken


User = get_user_model()


@override_settings(
    AUTH_MAX_FAILED_LOGIN_ATTEMPTS=3,
    AUTH_LOCKOUT_DURATION=timedelta(minutes=15),
)
class AuthenticationServiceTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

        self.refresh_token_service = Mock()
        self.refresh_token_service.issue.return_value = SimpleNamespace(
            raw_token="raw-refresh-token",
            expires_at=self.now + timedelta(days=7),
        )

        self.access_token_service = Mock()
        self.access_token_service.issue.return_value = (
            "v4.public.test-access-token"
        )

        self.service = AuthenticationService(
            refresh_token_service=self.refresh_token_service,
            access_token_service=self.access_token_service,
            clock=lambda: self.now,
        )

        self.user = User.objects.create_user(
            username="dipesh",
            email="dipesh@example.com",
            password="StrongPassword@123",
            status=User.Status.ACTIVE,
        )

    def test_successful_login_returns_both_tokens(self):
        result = self.service.login(
            email="dipesh@example.com",
            password="StrongPassword@123",
            device_info="Firefox on Linux",
            ip_address="127.0.0.1",
        )

        self.user.refresh_from_db()

        self.assertEqual(result.user, self.user)
        self.assertEqual(
            result.access_token,
            "v4.public.test-access-token",
        )
        self.assertEqual(
            result.refresh_token.raw_token,
            "raw-refresh-token",
        )
        self.assertEqual(self.user.failed_login_count, 0)
        self.assertIsNone(self.user.locked_until)
        self.assertEqual(self.user.last_login_at, self.now)

        self.refresh_token_service.issue.assert_called_once_with(
            user=self.user,
            device_info="Firefox on Linux",
            ip_address="127.0.0.1",
        )
        self.access_token_service.issue.assert_called_once_with(
            user=self.user,
        )

        event = AuthEvent.objects.get(
            user=self.user,
            event_type=AuthEvent.Kind.LOGIN,
        )
        self.assertEqual(event.ip_address, "127.0.0.1")
        self.assertEqual(event.user_agent, "Firefox on Linux")

    def test_wrong_password_increments_failure_count(self):
        with self.assertRaises(InvalidCredentialsError):
            self.service.login(
                email="dipesh@example.com",
                password="incorrect-password",
            )

        self.user.refresh_from_db()

        self.assertEqual(self.user.failed_login_count, 1)
        self.refresh_token_service.issue.assert_not_called()
        self.access_token_service.issue.assert_not_called()

    def test_unknown_user_is_rejected_without_issuing_tokens(self):
        with self.assertRaises(InvalidCredentialsError):
            self.service.login(
                email="missing@example.com",
                password="incorrect-password",
            )

        self.refresh_token_service.issue.assert_not_called()
        self.access_token_service.issue.assert_not_called()

    def test_failure_threshold_locks_account_and_records_event(self):
        for _ in range(2):
            with self.assertRaises(InvalidCredentialsError):
                self.service.login(
                    email="dipesh@example.com",
                    password="incorrect-password",
                )

        with self.assertRaises(AccountLockedError) as raised:
            self.service.login(
                email="dipesh@example.com",
                password="incorrect-password",
                device_info="Firefox on Linux",
                ip_address="127.0.0.1",
            )

        self.user.refresh_from_db()

        expected_unlock_time = self.now + timedelta(minutes=15)
        self.assertEqual(self.user.failed_login_count, 3)
        self.assertEqual(self.user.locked_until, expected_unlock_time)
        self.assertEqual(
            raised.exception.details,
            {"locked_until": expected_unlock_time.isoformat()},
        )

        event = AuthEvent.objects.get(
            user=self.user,
            event_type=AuthEvent.Kind.LOCKOUT,
        )
        self.assertEqual(event.ip_address, "127.0.0.1")
        self.assertEqual(event.user_agent, "Firefox on Linux")
        self.refresh_token_service.issue.assert_not_called()
        self.access_token_service.issue.assert_not_called()

    def test_correct_password_is_rejected_during_active_lock(self):
        self.user.failed_login_count = 3
        self.user.locked_until = self.now + timedelta(minutes=5)
        self.user.save(
            update_fields=["failed_login_count", "locked_until"]
        )

        with self.assertRaises(AccountLockedError):
            self.service.login(
                email="dipesh@example.com",
                password="StrongPassword@123",
            )

        self.refresh_token_service.issue.assert_not_called()
        self.access_token_service.issue.assert_not_called()

    def test_inactive_account_is_rejected(self):
        self.user.status = User.Status.SUSPENDED
        self.user.save(update_fields=["status"])

        with self.assertRaises(AccountInactiveError):
            self.service.login(
                email="dipesh@example.com",
                password="StrongPassword@123",
            )

        self.refresh_token_service.issue.assert_not_called()
        self.access_token_service.issue.assert_not_called()

    def test_successful_login_clears_expired_lock(self):
        self.user.failed_login_count = 3
        self.user.locked_until = self.now - timedelta(minutes=1)
        self.user.save(
            update_fields=["failed_login_count", "locked_until"]
        )

        self.service.login(
            email="dipesh@example.com",
            password="StrongPassword@123",
        )

        self.user.refresh_from_db()

        self.assertEqual(self.user.failed_login_count, 0)
        self.assertIsNone(self.user.locked_until)
        self.refresh_token_service.issue.assert_called_once()
        self.access_token_service.issue.assert_called_once()

    def test_failed_login_after_expired_lock_starts_new_counter(self):
        self.user.failed_login_count = 3
        self.user.locked_until = self.now - timedelta(minutes=1)
        self.user.save(
            update_fields=["failed_login_count", "locked_until"]
        )

        with self.assertRaises(InvalidCredentialsError):
            self.service.login(
                email="dipesh@example.com",
                password="incorrect-password",
            )

        self.user.refresh_from_db()

        self.assertEqual(self.user.failed_login_count, 1)
        self.assertIsNone(self.user.locked_until)

    def test_refresh_rotates_refresh_token_and_issues_access_token(self):
        replacement = SimpleNamespace(
            raw_token="replacement-refresh-token",
            expires_at=self.now + timedelta(days=7),
            user=self.user,
        )
        self.refresh_token_service.rotate.return_value = replacement
        self.access_token_service.issue.return_value = "v4.public.replacement"

        result = self.service.refresh(
            raw_refresh_token="current-refresh-token"
        )

        self.assertEqual(result.refresh_token, replacement)
        self.assertEqual(result.access_token, "v4.public.replacement")
        self.refresh_token_service.rotate.assert_called_once_with(
            "current-refresh-token"
        )
        self.access_token_service.issue.assert_called_once_with(user=self.user)

    def test_logout_revokes_token_and_records_event(self):
        self.refresh_token_service.revoke.return_value = RevokedRefreshToken(
            user=self.user,
            was_already_revoked=False,
        )

        result = self.service.logout(
            raw_refresh_token="raw-refresh-token",
            device_info="Firefox on Linux",
            ip_address="127.0.0.1",
        )

        self.assertTrue(result)
        event = AuthEvent.objects.get(
            user=self.user,
            event_type=AuthEvent.Kind.LOGOUT,
        )
        self.assertEqual(event.ip_address, "127.0.0.1")
        self.assertEqual(event.user_agent, "Firefox on Linux")

    def test_repeated_logout_does_not_duplicate_event(self):
        self.refresh_token_service.revoke.return_value = RevokedRefreshToken(
            user=self.user,
            was_already_revoked=True,
        )

        result = self.service.logout(
            raw_refresh_token="revoked-refresh-token"
        )

        self.assertTrue(result)
        self.assertFalse(
            AuthEvent.objects.filter(
                user=self.user,
                event_type=AuthEvent.Kind.LOGOUT,
            ).exists()
        )

    def test_logout_with_unknown_token_is_idempotent(self):
        self.refresh_token_service.revoke.return_value = None

        result = self.service.logout(
            raw_refresh_token="missing-refresh-token"
        )

        self.assertFalse(result)
        self.assertFalse(
            AuthEvent.objects.filter(event_type=AuthEvent.Kind.LOGOUT).exists()
        )
