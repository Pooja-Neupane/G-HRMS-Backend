from datetime import timedelta
from uuid import uuid4



from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from account.models import AuthEvent
from authentication.repositories import (
    UserRepository,
    RefreshTokenRepository,
    AuthEventRepository
    )

User = get_user_model()

class UserRepositoryTest(TestCase):
    def setUp(self):
        self.repository = UserRepository()
        self.user = User.objects.create_user(
            username = "dipesh",
            email="dipesh@example.com",
            password="devDipesh@123"
        )
    def test_find_by_login_returns_user(self):
        result = self.repository.find_by_login("dipesh")
        self.assertEqual(result,self.user)

    def test_find_by_login_returns_none_when_missing(self):
        result = self.repository.find_by_login("missing-user")
        self.assertIsNone(result)

    def test_find_for_update_by_login_returns_locked_user(self):
        result = self.repository.find_for_update_by_login("dipesh")
        self.assertEqual(result,self.user)

    def test_get_for_update_by_id_returns_user(self):
        result = self.repository.get_for_update_by_id(self.user.pk)

        self.assertEqual(result, self.user)

    def test_save_updates_selected_fields(self):
        self.user.failed_login_count = 3

        result = self.repository.save(
            self.user,
            update_fields=["failed_login_count"],
        )

        self.user.refresh_from_db()

        self.assertEqual(result, self.user)
        self.assertEqual(self.user.failed_login_count, 3)

class RefreshTokenRepositoryTests(TestCase):
    def setUp(self):
        self.repository = RefreshTokenRepository()
        self.user = User.objects.create_user(
            username="dipesh",
            password="devDipesh@123",
        )
        self.expires_at = timezone.now() + timedelta(days=7)

    def create_token(self, **overrides):
        values = {
            "user": self.user,
            "token_hash": "a" * 64,
            "expires_at": self.expires_at,
            "device_info": "repository-test",
            "ip_address": "127.0.0.1",
        }
        values.update(overrides)
        return self.repository.create(**values)

    def test_create_persists_token_hash_and_metadata(self):
        token = self.create_token()

        self.assertEqual(token.user, self.user)
        self.assertEqual(token.token_hash, "a" * 64)
        self.assertEqual(token.device_info, "repository-test")
        self.assertEqual(token.ip_address, "127.0.0.1")
        self.assertFalse(token.is_revoked)

    def test_find_by_hash_returns_token(self):
        token = self.create_token()

        result = self.repository.find_by_hash(token.token_hash)

        self.assertEqual(result, token)

    def test_find_for_update_by_hash_returns_locked_token(self):
        token = self.create_token()

        result = self.repository.find_for_update_by_hash(token.token_hash)

        self.assertEqual(result, token)
        self.assertEqual(result.user, self.user)

    def test_revoke_updates_token(self):
        token = self.create_token()
        revoked_at = timezone.now()

        result = self.repository.revoke(
            token,
            rotated_at=revoked_at,
        )

        token.refresh_from_db()

        self.assertEqual(result, token)
        self.assertTrue(token.is_revoked)
        self.assertEqual(token.rotated_at, revoked_at)

    def test_revoke_family_only_updates_matching_active_tokens(self):
        family_id = uuid4()
        first = self.create_token(
            token_hash="b" * 64,
            family_id=family_id,
        )
        second = self.create_token(
            token_hash="c" * 64,
            family_id=family_id,
        )
        unrelated = self.create_token(
            token_hash="d" * 64,
        )
        revoked_at = timezone.now()

        updated_count = self.repository.revoke_family(
            family_id,
            rotated_at=revoked_at,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        unrelated.refresh_from_db()

        self.assertEqual(updated_count, 2)
        self.assertTrue(first.is_revoked)
        self.assertTrue(second.is_revoked)
        self.assertFalse(unrelated.is_revoked)

class AuthEventRepositoryTests(TestCase):
    def setUp(self):
        self.repository = AuthEventRepository()
        self.user = User.objects.create_user(
            username="dipesh",
            password="devDipesh@123",
        )

    def test_create_persists_security_event(self):
        occurred_at = timezone.now()

        event = self.repository.create(
            event_type=AuthEvent.Kind.TOKEN_REUSE,
            user=self.user,
            ip_address="127.0.0.1",
            user_agent="Firefox on Linux",
            occurred_at=occurred_at,
        )

        event.refresh_from_db()

        self.assertEqual(event.event_type, AuthEvent.Kind.TOKEN_REUSE)
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.ip_address, "127.0.0.1")
        self.assertEqual(event.user_agent, "Firefox on Linux")
        self.assertEqual(event.occurred_at, occurred_at)

    def test_security_event_cannot_be_updated(self):
        event = self.repository.create(
            event_type=AuthEvent.Kind.LOGIN,
            user=self.user,
        )
        event.event_type = AuthEvent.Kind.LOGOUT

        with self.assertRaises(PermissionError):
            event.save()

    def test_security_event_cannot_be_deleted(self):
        event = self.repository.create(
            event_type=AuthEvent.Kind.LOGIN,
            user=self.user,
        )

        with self.assertRaises(PermissionError):
            event.delete()