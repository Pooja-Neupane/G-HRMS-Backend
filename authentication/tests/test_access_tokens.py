import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pyseto
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from django.test import SimpleTestCase, override_settings

from authentication.exceptions import InvalidAccessTokenError
from authentication.services import PasetoAccessTokenService


@override_settings(
    PASETO_ISSUER="g-hrms-backend",
    PASETO_AUDIENCE="g-hrms-api",
    PASETO_ACCESS_TOKEN_LIFETIME=timedelta(minutes=5),
    PASETO_CLOCK_SKEW_SECONDS=30,
)
class PasetoAccessTokenServiceTests(SimpleTestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)

        directory = Path(self.temporary_directory.name)
        self.private_key_path = directory / "private.pem"
        self.public_key_path = directory / "public.pem"

        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        self.private_key_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        self.public_key_path.write_bytes(
            public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

        self.current_time = datetime(
            2026,
            1,
            1,
            12,
            0,
            tzinfo=UTC,
        )
        self.user = SimpleNamespace(
            pk=123,
            role="VIEWER",
        )
        self.service = self.create_service()

    def create_service(self):
        return PasetoAccessTokenService(
            private_key_path=self.private_key_path,
            public_key_path=self.public_key_path,
            clock=lambda: self.current_time,
            token_id_factory=lambda: "test-token-id",
        )

    def test_issue_and_verify_access_token(self):
        token = self.service.issue(user=self.user)

        claims = self.service.verify(token)

        self.assertTrue(token.startswith("v4.public."))
        self.assertEqual(claims.user_id, "123")
        self.assertEqual(claims.role, "VIEWER")
        self.assertEqual(claims.token_id, "test-token-id")
        self.assertEqual(claims.issued_at, self.current_time)
        self.assertEqual(
            claims.expires_at,
            self.current_time + timedelta(minutes=5),
        )

    def test_payload_contains_only_approved_claims(self):
        token = self.service.issue(user=self.user)

        decoded = pyseto.decode(
            self.service.public_key,
            token,
            implicit_assertion=self.service.implicit_assertion,
        )
        payload = json.loads(decoded.payload)

        self.assertEqual(
            set(payload),
            {
                "sub",
                "role",
                "jti",
                "iss",
                "aud",
                "iat",
                "exp",
                "type",
            },
        )

    def test_expired_token_is_rejected(self):
        token = self.service.issue(user=self.user)
        self.current_time += timedelta(minutes=6)

        with self.assertRaises(InvalidAccessTokenError):
            self.service.verify(token)

    def test_tampered_token_is_rejected(self):
        token = self.service.issue(user=self.user)
        sections = token.split(".")
        payload_and_signature = list(sections[2])
        index = len(payload_and_signature) // 2
        payload_and_signature[index] = (
            "A" if payload_and_signature[index] != "A" else "B"
        )
        sections[2] = "".join(payload_and_signature)
        tampered_token = ".".join(sections)

        with self.assertRaises(InvalidAccessTokenError):
            self.service.verify(tampered_token)

    def test_token_is_bound_to_configured_audience(self):
        token = self.service.issue(user=self.user)

        with override_settings(PASETO_AUDIENCE="different-api"):
            different_service = self.create_service()

        with self.assertRaises(InvalidAccessTokenError):
            different_service.verify(token)

    def test_token_signed_by_another_key_is_rejected(self):
        other_private_key = Ed25519PrivateKey.generate()
        other_public_key_path = (
            Path(self.temporary_directory.name) / "other-public.pem"
        )
        other_public_key_path.write_bytes(
            other_private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

        other_service = PasetoAccessTokenService(
            private_key_path=self.private_key_path,
            public_key_path=other_public_key_path,
            clock=lambda: self.current_time,
            token_id_factory=lambda: "other-token-id",
        )
        token = self.service.issue(user=self.user)

        with self.assertRaises(InvalidAccessTokenError):
            other_service.verify(token)

    def test_malformed_token_is_rejected(self):
        with self.assertRaises(InvalidAccessTokenError):
            self.service.verify("not-a-paseto-token")