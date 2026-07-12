import re
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.exceptions import InvalidRefreshTokenError
from authentication.views import LoginView, LogoutView, RefreshView


User = get_user_model()


@override_settings(
    AUTH_REFRESH_COOKIE_NAME="ghrms_refresh",
    AUTH_REFRESH_COOKIE_SECURE=False,
    AUTH_REFRESH_COOKIE_SAMESITE="Strict",
    AUTH_REFRESH_COOKIE_PATH="/",
    AUTH_REFRESH_TOKEN_LIFETIME=timedelta(days=7),
    PASETO_ACCESS_TOKEN_LIFETIME=timedelta(minutes=5),
)
class AuthenticationApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = SimpleNamespace(
            pk=123,
            username="dipesh",
            role="VIEWER",
        )

    def csrf_token(self):
        response = self.client.get(reverse("authentication:csrf"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)
        return response.data["csrf_token"]

    def post(self, name, data=None):
        return self.client.post(
            reverse(f"authentication:{name}"),
            data=data or {},
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

    def refresh_token(self, raw_token="raw-refresh-token"):
        return SimpleNamespace(
            raw_token=raw_token,
            expires_at=timezone.now() + timedelta(days=7),
            user=self.user,
        )

    def test_login_requires_csrf(self):
        response = self.client.post(
            reverse("authentication:login"),
            {"email": "dipesh@example.com", "password": "secret"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_refresh_and_logout_require_csrf(self):
        self.client.cookies["ghrms_refresh"] = "raw-refresh-token"

        for endpoint in ("refresh", "logout"):
            with self.subTest(endpoint=endpoint):
                response = self.client.post(
                    reverse(f"authentication:{endpoint}"),
                    {},
                    format="json",
                )
                self.assertEqual(response.status_code, 403)

    def test_login_sets_httponly_refresh_cookie(self):
        service = Mock()
        service.login.return_value = SimpleNamespace(
            user=self.user,
            access_token="v4.public.access-token",
            refresh_token=self.refresh_token(),
        )

        with patch.object(LoginView, "service_class", return_value=service):
            response = self.post(
                "login",
                {"email": "dipesh@example.com", "password": "secret"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["access_token"], "v4.public.access-token")
        self.assertNotIn("refresh_token", response.data)
        self.assertEqual(response.data["expires_in"], 300)

        cookie = response.cookies["ghrms_refresh"]
        self.assertEqual(cookie.value, "raw-refresh-token")
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertEqual(cookie["path"], "/")

        service.login.assert_called_once_with(
            email="dipesh@example.com",
            password="secret",
            device_info="",
            ip_address="127.0.0.1",
        )

    def test_login_validation_uses_global_error_envelope(self):
        response = self.post("login", {"email": "dipesh@example.com"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "validation_error")
        self.assertIn("password", response.data["error"]["details"])

    def test_refresh_rotates_cookie_and_returns_access_token(self):
        service = Mock()
        service.refresh.return_value = SimpleNamespace(
            access_token="v4.public.replacement",
            refresh_token=self.refresh_token("replacement-refresh-token"),
        )
        self.client.cookies["ghrms_refresh"] = "current-refresh-token"

        with patch.object(RefreshView, "service_class", return_value=service):
            response = self.post("refresh")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["access_token"], "v4.public.replacement")
        self.assertNotIn("refresh_token", response.data)
        self.assertEqual(
            response.cookies["ghrms_refresh"].value,
            "replacement-refresh-token",
        )
        service.refresh.assert_called_once_with(
            raw_refresh_token="current-refresh-token"
        )

    def test_invalid_refresh_clears_cookie(self):
        service = Mock()
        service.refresh.side_effect = InvalidRefreshTokenError()
        self.client.cookies["ghrms_refresh"] = "invalid-refresh-token"

        with patch.object(RefreshView, "service_class", return_value=service):
            response = self.post("refresh")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.data["error"]["code"],
            "invalid_refresh_token",
        )
        self.assertEqual(response.cookies["ghrms_refresh"]["max-age"], 0)

    def test_logout_revokes_token_and_clears_cookie(self):
        service = Mock()
        service.logout.return_value = True
        self.client.cookies["ghrms_refresh"] = "raw-refresh-token"

        with patch.object(LogoutView, "service_class", return_value=service):
            response = self.post("logout")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.cookies["ghrms_refresh"]["max-age"], 0)
        service.logout.assert_called_once_with(
            raw_refresh_token="raw-refresh-token",
            device_info="",
            ip_address="127.0.0.1",
        )

    def test_logout_without_cookie_remains_idempotent(self):
        service = Mock()

        with patch.object(LogoutView, "service_class", return_value=service):
            response = self.post("logout")

        self.assertEqual(response.status_code, 204)
        service.logout.assert_not_called()


@override_settings(
    AUTH_REFRESH_COOKIE_NAME="ghrms_refresh",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    AUTH_SIGNUP_OTP_LENGTH=6,
    AUTH_SIGNUP_OTP_TTL=timedelta(minutes=10),
    AUTH_SIGNUP_OTP_MAX_ATTEMPTS=3,
    AUTH_SIGNUP_OTP_RESEND_COOLDOWN=timedelta(seconds=60),
    AUTH_SIGNUP_CACHE_PREFIX="test:api:signup",
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "signup-api-tests",
        }
    },
)
class SignupApiTests(TestCase):
    """End-to-end OTP signup tests against the real service and database."""

    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf_token(self):
        response = self.client.get(reverse("authentication:csrf"))
        self.assertEqual(response.status_code, 200)
        return response.data["csrf_token"]

    def post(self, name, data, with_csrf=True):
        headers = {}
        if with_csrf:
            headers["HTTP_X_CSRFTOKEN"] = self.csrf_token()
        return self.client.post(
            reverse(f"authentication:{name}"),
            data=data,
            format="json",
            **headers,
        )

    def valid_payload(self, **overrides):
        payload = {
            "username": "newcomer",
            "email": "newcomer@example.com",
            "password": "StrongPassword@123",
            "password_confirm": "StrongPassword@123",
        }
        payload.update(overrides)
        return payload

    def sent_otp(self):
        self.assertTrue(mail.outbox, "expected a verification email")
        match = re.search(r"\b(\d{6})\b", mail.outbox[-1].body)
        self.assertIsNotNone(match, "no OTP found in email body")
        return match.group(1)

    def test_signup_requires_csrf(self):
        response = self.post("signup", self.valid_payload(), with_csrf=False)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_signup_emails_code_without_persisting_account(self):
        response = self.post("signup", self.valid_payload())

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["email"], "newcomer@example.com")
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["newcomer@example.com"])

    def test_full_flow_creates_invited_user_on_verification(self):
        self.post("signup", self.valid_payload())
        otp = self.sent_otp()

        response = self.post(
            "signup-verify",
            {"email": "newcomer@example.com", "otp": otp},
        )

        self.assertEqual(response.status_code, 201)
        self.assertNotIn("access_token", response.data)
        self.assertNotIn("ghrms_refresh", response.cookies)

        body = response.data["user"]
        self.assertEqual(body["status"], User.Status.INVITED)
        self.assertEqual(body["role"], User.Role.VIEWER)

        user = User.objects.get(username="newcomer")
        self.assertEqual(user.status, User.Status.INVITED)
        self.assertTrue(user.check_password("StrongPassword@123"))

    def test_verify_rejects_wrong_code(self):
        self.post("signup", self.valid_payload())

        response = self.post(
            "signup-verify",
            {"email": "newcomer@example.com", "otp": "000000"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "invalid_otp")
        self.assertEqual(User.objects.count(), 0)

    def test_verify_without_pending_registration_returns_404(self):
        response = self.post(
            "signup-verify",
            {"email": "ghost@example.com", "otp": "123456"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.data["error"]["code"],
            "pending_registration_not_found",
        )

    def test_resend_is_throttled_immediately_after_signup(self):
        self.post("signup", self.valid_payload())

        response = self.post(
            "signup-resend", {"email": "newcomer@example.com"}
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(
            response.data["error"]["code"], "otp_resend_throttled"
        )

    def test_signup_rejects_duplicate_username(self):
        User.objects.create_user(
            username="newcomer",
            email="existing@example.com",
            password="StrongPassword@123",
        )

        response = self.post("signup", self.valid_payload())

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "validation_error")
        self.assertIn("username", response.data["error"]["details"])
        self.assertEqual(len(mail.outbox), 0)

    def test_signup_rejects_password_mismatch(self):
        response = self.post(
            "signup",
            self.valid_payload(password_confirm="DifferentPassword@123"),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "validation_error")
        self.assertIn("password_confirm", response.data["error"]["details"])
        self.assertEqual(len(mail.outbox), 0)

    def test_signup_rejects_weak_password(self):
        response = self.post(
            "signup",
            self.valid_payload(password="123", password_confirm="123"),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "validation_error")
        self.assertIn("password", response.data["error"]["details"])
