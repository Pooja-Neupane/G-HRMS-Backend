from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from authentication.authentication import PasetoAuthentication
from authentication.services.access_tokens import (
    AccessTokenClaims,
    PasetoAccessTokenService,
)


User = get_user_model()


class PasetoAuthenticationTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.service = PasetoAccessTokenService()
        self.auth = PasetoAuthentication()
        self.auth.token_service = self.service
        self.user = User.objects.create_user(
            username="agent",
            email="agent@example.com",
            password="StrongPassword@123",
            status=User.Status.ACTIVE,
        )

    def _request(self, authorization=None):
        headers = {}
        if authorization is not None:
            headers["HTTP_AUTHORIZATION"] = authorization
        return self.factory.get("/", **headers)

    def test_valid_bearer_token_authenticates(self):
        token = self.service.issue(user=self.user)

        user, claims = self.auth.authenticate(self._request(f"Bearer {token}"))

        self.assertEqual(user, self.user)
        self.assertEqual(claims.user_id, str(self.user.pk))

    def test_no_authorization_header_returns_none(self):
        self.assertIsNone(self.auth.authenticate(self._request()))

    def test_non_bearer_scheme_is_ignored(self):
        self.assertIsNone(
            self.auth.authenticate(self._request("Basic dXNlcjpwYXNz"))
        )

    def test_missing_credentials_is_rejected(self):
        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(self._request("Bearer"))

    def test_invalid_token_is_rejected(self):
        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(self._request("Bearer not-a-real-token"))

    def test_inactive_user_is_rejected(self):
        token = self.service.issue(user=self.user)
        self.user.status = User.Status.INVITED
        self.user.save(update_fields=["status"])

        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(self._request(f"Bearer {token}"))

    def test_token_for_unknown_user_is_rejected(self):
        now = datetime.now(UTC)
        fake_service = Mock()
        fake_service.verify.return_value = AccessTokenClaims(
            user_id="999999",
            role="VIEWER",
            token_id="t",
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
        )
        self.auth.token_service = fake_service

        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(self._request("Bearer any-token"))
