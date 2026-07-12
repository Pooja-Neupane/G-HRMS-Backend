from datetime import UTC, datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from account.models import RefreshToken, AuthEvent
from authentication.exceptions import (
    InvalidRefreshTokenError,
    TokenReuseDetectedError,
)
from authentication.services import RefreshTokenService


User = get_user_model()


@override_settings(AUTH_REFRESH_TOKEN_LIFETIME=timedelta(days=7))
class TokenServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dipesh",
            password="devDipesh@123",
        )
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        self.raw_tokens = iter(
            [
                "raw-token-one",
                "raw-token-two",
                "raw-token-three",
            ]
        )
        self.service = RefreshTokenService(
            token_factory=lambda: next(self.raw_tokens),
            clock=lambda: self.now,
        )

    def test_hash_token_is_deterministic(self):
        first = self.service.hash_token("refresh-token")
        second = self.service.hash_token("refresh-token")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertNotEqual(first, "refresh-token")

    def test_issue_returns_raw_token_but_stores_only_hash(self):
        issued = self.service.issue(
            user=self.user,
            device_info="Firefox on Linux",
            ip_address="127.0.0.1",
        )

        stored = RefreshToken.objects.get(
            token_hash=self.service.hash_token(issued.raw_token)
        )

        self.assertEqual(issued.raw_token, "raw-token-one")
        self.assertNotEqual(stored.token_hash, issued.raw_token)
        self.assertEqual(
            issued.expires_at,
            self.now + timedelta(days=7),
        )
        self.assertEqual(stored.device_info, "Firefox on Linux")
        self.assertEqual(stored.ip_address, "127.0.0.1")
        self.assertEqual(issued.user, self.user)

    def test_rotate_revokes_current_and_creates_child(self):
        original = self.service.issue(user=self.user)
        original_record = RefreshToken.objects.get(
            token_hash=self.service.hash_token(original.raw_token)
        )

        replacement = self.service.rotate(original.raw_token)

        original_record.refresh_from_db()
        replacement_record = RefreshToken.objects.get(
            token_hash=self.service.hash_token(replacement.raw_token)
        )

        self.assertTrue(original_record.is_revoked)
        self.assertEqual(replacement.raw_token, "raw-token-two")
        self.assertFalse(replacement_record.is_revoked)
        self.assertEqual(
            replacement_record.family_id,
            original_record.family_id,
        )
        self.assertEqual(
            replacement_record.parent_id,
            original_record.id,
        )

    def test_invalid_token_is_rejected(self):
        with self.assertRaises(InvalidRefreshTokenError):
            self.service.rotate("unknown-token")

    def test_expired_token_is_revoked_before_error_is_raised(self):
        raw_token = "expired-raw-token"
        stored = RefreshToken.objects.create(
            user=self.user,
            token_hash=self.service.hash_token(raw_token),
            expires_at=self.now - timedelta(minutes=1),
        )

        with self.assertRaises(InvalidRefreshTokenError):
            self.service.rotate(raw_token)

        stored.refresh_from_db()

        self.assertTrue(stored.is_revoked)
        self.assertEqual(stored.rotated_at, self.now)

    def test_reusing_revoked_token_revokes_replacement_family(self):
        original = self.service.issue(user=self.user)
        replacement = self.service.rotate(original.raw_token)
        replacement_record = RefreshToken.objects.get(
            token_hash=self.service.hash_token(replacement.raw_token)
        )


        with self.assertLogs("ghrms.security", level="WARNING"):
            with self.assertRaises(TokenReuseDetectedError):
                self.service.rotate(original.raw_token)

        replacement_record.refresh_from_db()

        event = AuthEvent.objects.get(
            event_type= AuthEvent.Kind.TOKEN_REUSE,
            user=self.user,
        )
        
        self.assertEqual(event.ip_address,replacement_record.ip_address)
        self.assertEqual(event.user_agent,replacement_record.device_info)
        self.assertEqual(event.occurred_at,self.now)

        self.assertTrue(replacement_record.is_revoked)
        self.assertEqual(replacement_record.rotated_at, self.now)

    def test_revoke_is_idempotent(self):
        issued = self.service.issue(user=self.user)

        first_result = self.service.revoke(issued.raw_token)
        second_result = self.service.revoke(issued.raw_token)
        missing_result = self.service.revoke("missing-token")

        stored = RefreshToken.objects.get(
            token_hash=self.service.hash_token(issued.raw_token)
        )

        self.assertTrue(first_result)
        self.assertTrue(second_result)
        self.assertFalse(missing_result)
        self.assertTrue(stored.is_revoked)
