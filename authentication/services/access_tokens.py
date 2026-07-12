"""PASETO v4.public access-token issuance and verification."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pyseto
from django.conf import settings
from pyseto import Key, PysetoError

from authentication.exceptions import InvalidAccessTokenError


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: str
    role: str
    token_id: str
    issued_at: datetime
    expires_at: datetime


class PasetoAccessTokenService:
    """Issue and verify short-lived PASETO v4.public access tokens."""

    def __init__(
        self,
        *,
        private_key_path=None,
        public_key_path=None,
        clock: Callable[[], datetime] | None = None,
        token_id_factory: Callable[[], str] | None = None,
    ):
        self.clock = clock or (lambda: datetime.now(UTC))
        self.token_id_factory = token_id_factory or (
            lambda: str(uuid4())
        )

        # Check for environment variables first (for Render)
        private_key_pem = settings.PASETO_PRIVATE_KEY
        public_key_pem = settings.PASETO_PUBLIC_KEY

        if private_key_pem and public_key_pem:
            private_key_bytes = private_key_pem.encode("utf-8")
            public_key_bytes = public_key_pem.encode("utf-8")
        else:
            # Fall back to file-based keys (for local development)
            private_path = (
                private_key_path or settings.PASETO_PRIVATE_KEY_PATH
            )
            public_path = (
                public_key_path or settings.PASETO_PUBLIC_KEY_PATH
            )
            private_key_bytes = self._read_key(private_path)
            public_key_bytes = self._read_key(public_path)

        self.private_key = Key.new(
            version=4,
            purpose="public",
            key=private_key_bytes,
        )
        self.public_key = Key.new(
            version=4,
            purpose="public",
            key=public_key_bytes,
        )

        self.issuer = settings.PASETO_ISSUER
        self.audience = settings.PASETO_AUDIENCE
        self.lifetime = settings.PASETO_ACCESS_TOKEN_LIFETIME
        self.clock_skew = timedelta(
            seconds=settings.PASETO_CLOCK_SKEW_SECONDS
        )
        self.implicit_assertion = (
            f"{self.issuer}|{self.audience}"
        )

    def issue(self, *, user) -> str:
        now = self._normalise_datetime(self.clock())
        expires_at = now + self.lifetime
        token_id = self.token_id_factory()

        payload = {
            "sub": str(user.pk),
            "role": str(user.role),
            "jti": token_id,
            "iss": self.issuer,
            "aud": self.audience,
            "iat": now.isoformat(),
            "exp": expires_at.isoformat(),
            "type": "access",
        }

        footer = {
            "kid": self.public_key.to_paserk_id(),
        }

        token = pyseto.encode(
            self.private_key,
            payload,
            footer=footer,
            implicit_assertion=self.implicit_assertion,
            serializer=json,
        )

        return token.decode("utf-8")

    def verify(self, token: str) -> AccessTokenClaims:
        try:
            decoded = pyseto.decode(
                self.public_key,
                token,
                implicit_assertion=self.implicit_assertion,
            )

            payload = json.loads(decoded.payload)
            footer = (
                json.loads(decoded.footer)
                if decoded.footer
                else {}
            )

            return self._validate_claims(payload, footer)

        except InvalidAccessTokenError:
            raise
        except (
            PysetoError,
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
        ) as exc:
            raise InvalidAccessTokenError() from exc

    def _validate_claims(
        self,
        payload: dict,
        footer: dict,
    ) -> AccessTokenClaims:
        required_claims = {
            "sub",
            "role",
            "jti",
            "iss",
            "aud",
            "iat",
            "exp",
            "type",
        }

        if not isinstance(payload, dict):
            raise InvalidAccessTokenError()

        if not required_claims.issubset(payload):
            raise InvalidAccessTokenError()

        if payload["iss"] != self.issuer:
            raise InvalidAccessTokenError()

        if payload["aud"] != self.audience:
            raise InvalidAccessTokenError()

        if payload["type"] != "access":
            raise InvalidAccessTokenError()

        expected_key_id = self.public_key.to_paserk_id()
        if footer.get("kid") != expected_key_id:
            raise InvalidAccessTokenError()

        issued_at = self._parse_datetime(payload["iat"])
        expires_at = self._parse_datetime(payload["exp"])
        now = self._normalise_datetime(self.clock())

        if expires_at <= now:
            raise InvalidAccessTokenError()

        if issued_at > now + self.clock_skew:
            raise InvalidAccessTokenError()

        if expires_at <= issued_at:
            raise InvalidAccessTokenError()

        if not all(
            isinstance(payload[field], str) and payload[field]
            for field in ("sub", "role", "jti")
        ):
            raise InvalidAccessTokenError()

        return AccessTokenClaims(
            user_id=payload["sub"],
            role=payload["role"],
            token_id=payload["jti"],
            issued_at=issued_at,
            expires_at=expires_at,
        )

    @staticmethod
    def _read_key(path) -> bytes:
        try:
            return path.read_bytes()
        except (AttributeError, OSError) as exc:
            raise RuntimeError(
                f"Unable to read PASETO key: {path}"
            ) from exc

    @staticmethod
    def _parse_datetime(value) -> datetime:
        if not isinstance(value, str):
            raise InvalidAccessTokenError()

        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise InvalidAccessTokenError() from exc

        if parsed.tzinfo is None:
            raise InvalidAccessTokenError()

        return parsed.astimezone(UTC)

    @staticmethod
    def _normalise_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Token clock must return a timezone-aware datetime.")

        return value.astimezone(UTC)