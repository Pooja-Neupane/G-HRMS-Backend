from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from authentication.exceptions import (
    InvalidOtpError,
    OtpResendThrottledError,
    PendingRegistrationNotFoundError,
    TooManyOtpAttemptsError,
    UsernameAlreadyExistsError,
)
from authentication.services import SignupService


User = get_user_model()


@override_settings(
    AUTH_SIGNUP_OTP_LENGTH=6,
    AUTH_SIGNUP_OTP_TTL=timedelta(minutes=10),
    AUTH_SIGNUP_OTP_MAX_ATTEMPTS=3,
    AUTH_SIGNUP_OTP_RESEND_COOLDOWN=timedelta(seconds=60),
    AUTH_SIGNUP_OTP_MAX_RESENDS=2,
    AUTH_SIGNUP_CACHE_PREFIX="test:signup:pending",
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "signup-service-tests",
        }
    },
)
class SignupServiceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        self.email = Mock()
        self.service = SignupService(
            otp_email_sender=self.email,
            otp_factory=lambda: "123456",
            clock=lambda: self.now,
        )

    def start(self, **overrides):
        payload = {
            "username": "newcomer",
            "email": "Newcomer@Example.com",
            "password": "StrongPassword@123",
        }
        payload.update(overrides)
        return self.service.start(**payload)

    def test_start_stashes_pending_without_creating_user(self):
        result = self.start()

        self.assertEqual(User.objects.count(), 0)
        self.email.assert_called_once()
        _, kwargs = self.email.call_args
        self.assertEqual(kwargs["otp"], "123456")
        self.assertEqual(kwargs["email"], "newcomer@example.com")
        self.assertEqual(result.email, "newcomer@example.com")
        self.assertEqual(result.expires_in, 600)
        self.assertEqual(result.resend_available_in, 60)

    def test_verify_persists_invited_viewer_with_usable_password(self):
        self.start()

        result = self.service.verify(email="newcomer@example.com", otp="123456")

        user = result.user
        user.refresh_from_db()
        self.assertEqual(user.username, "newcomer")
        self.assertEqual(user.email, "newcomer@example.com")
        self.assertEqual(user.status, User.Status.INVITED)
        self.assertEqual(user.role, User.Role.VIEWER)
        self.assertTrue(user.check_password("StrongPassword@123"))
        self.assertEqual(user.password_changed_at, self.now)

        # The pending entry is consumed; verifying again finds nothing.
        with self.assertRaises(PendingRegistrationNotFoundError):
            self.service.verify(email="newcomer@example.com", otp="123456")

    def test_wrong_code_is_rejected_without_creating_user(self):
        self.start()

        with self.assertRaises(InvalidOtpError):
            self.service.verify(email="newcomer@example.com", otp="000000")

        self.assertEqual(User.objects.count(), 0)

        # A subsequent correct code still works (attempts below the limit).
        result = self.service.verify(email="newcomer@example.com", otp="123456")
        self.assertTrue(User.objects.filter(pk=result.user.pk).exists())

    def test_exhausting_attempts_purges_pending_registration(self):
        self.start()

        for _ in range(2):
            with self.assertRaises(InvalidOtpError):
                self.service.verify(email="newcomer@example.com", otp="000000")

        with self.assertRaises(TooManyOtpAttemptsError):
            self.service.verify(email="newcomer@example.com", otp="000000")

        # Pending registration is gone even for the correct code.
        with self.assertRaises(PendingRegistrationNotFoundError):
            self.service.verify(email="newcomer@example.com", otp="123456")
        self.assertEqual(User.objects.count(), 0)

    def test_verify_without_pending_registration_is_rejected(self):
        with self.assertRaises(PendingRegistrationNotFoundError):
            self.service.verify(email="ghost@example.com", otp="123456")

    def test_resend_is_throttled_during_cooldown(self):
        self.start()

        with self.assertRaises(OtpResendThrottledError) as raised:
            self.service.resend(email="newcomer@example.com")

        self.assertIn("retry_after", raised.exception.details)

    def test_resend_after_cooldown_reissues_and_resets_attempts(self):
        self.start()

        # One wrong attempt, then wait out the cooldown and resend.
        with self.assertRaises(InvalidOtpError):
            self.service.verify(email="newcomer@example.com", otp="000000")

        self.now = self.now + timedelta(seconds=61)
        result = self.service.resend(email="newcomer@example.com")

        self.assertEqual(result.email, "newcomer@example.com")
        self.assertEqual(self.email.call_count, 2)

        # Attempts were reset, so the fresh code verifies successfully.
        verified = self.service.verify(email="newcomer@example.com", otp="123456")
        self.assertTrue(User.objects.filter(pk=verified.user.pk).exists())

    def test_resend_without_pending_registration_is_rejected(self):
        with self.assertRaises(PendingRegistrationNotFoundError):
            self.service.resend(email="ghost@example.com")

    def test_username_taken_while_pending_is_rejected_at_verify(self):
        User.objects.create_user(
            username="newcomer",
            email="someone-else@example.com",
            password="StrongPassword@123",
        )

        self.start()

        with self.assertRaises(UsernameAlreadyExistsError):
            self.service.verify(email="newcomer@example.com", otp="123456")

        # The pending registration is cleared after the conflict.
        with self.assertRaises(PendingRegistrationNotFoundError):
            self.service.verify(email="newcomer@example.com", otp="123456")
