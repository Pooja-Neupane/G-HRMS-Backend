"""Refresh-token issuance, rotation and revocation workflows."""

from __future__ import annotations

import hashlib
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from account.models import AuthEvent
from authentication.exceptions import (
    InvalidRefreshTokenError,
    TokenReuseDetectedError,
)
from authentication.repositories import (
    AuthEventRepository,
    RefreshTokenRepository)


security_logger = logging.getLogger("ghrms.security")


@dataclass(frozen=True, slots=True)
class IssuedRefreshToken:
    """Raw token returned once to the client."""

    raw_token: str
    expires_at: datetime
    user: object


@dataclass(frozen=True, slots=True)
class RevokedRefreshToken:
    """Identity associated with an idempotent token revocation."""

    user: object
    was_already_revoked: bool


class RefreshTokenService:
    """Coordinate secure refresh-token lifecycle operations."""

    def __init__(
        self,
        *,
        repository: RefreshTokenRepository | None = None,
        event_repository: AuthEventRepository | None = None,
        token_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.repository = repository or RefreshTokenRepository()
        self.event_repository = event_repository or AuthEventRepository()
        self.token_factory = token_factory or self._generate_token
        self.clock = clock or timezone.now

    @staticmethod
    def _generate_token() -> str:
        return secrets.token_urlsafe(48)

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    def issue(
        self,
        *,
        user,
        device_info: str = "",
        ip_address: str | None = None,
    ) -> IssuedRefreshToken:
        """Create a new refresh-token family."""
        return self._issue(
            user=user,
            now=self.clock(),
            device_info=device_info,
            ip_address=ip_address,
        )

    def rotate(self, raw_token: str) -> IssuedRefreshToken:
        """
        Revoke the current token and issue its replacement.

        The current database row is locked so two concurrent refresh requests
        cannot both successfully rotate the same token.
        """
        token_hash = self.hash_token(raw_token)
        pending_error = None
        issued_token = None

        with transaction.atomic():
            current = self.repository.find_for_update_by_hash(token_hash)

            if current is None:
                raise InvalidRefreshTokenError()

            now = self.clock()

            if current.is_revoked:
                self.repository.revoke_family(
                    current.family_id,
                    rotated_at=now,
                )

                self.event_repository.create(
                    event_type=AuthEvent.Kind.TOKEN_REUSE,
                    user=current.user,
                    ip_address=current.ip_address,
                    user_agent=current.device_info,
                    occurred_at=now,
                )

                security_logger.warning(
                    "auth.token_reuse_detected",
                    extra={
                        "user_id": str(current.user_id),
                        "client_ip": current.ip_address,
                    },
                )
                pending_error = TokenReuseDetectedError()

            elif current.expires_at <= now:
                self.repository.revoke(
                    current,
                    rotated_at=now,
                )
                pending_error = InvalidRefreshTokenError()

            else:
                self.repository.revoke(
                    current,
                    rotated_at=now,
                )
                issued_token = self._issue(
                    user=current.user,
                    now=now,
                    family_id=current.family_id,
                    parent=current,
                    device_info=current.device_info,
                    ip_address=current.ip_address,
                )

        # Raise after transaction.atomic() exits so security revocations commit.
        if pending_error is not None:
            raise pending_error

        if issued_token is None:
            raise RuntimeError("Token rotation completed without a result.")

        return issued_token

    def revoke(self, raw_token: str) -> RevokedRefreshToken | None:
        """
        Revoke one refresh token.

        Returns None when the token does not exist. Repeated revocation is
        idempotent and returns the token owner with the previous state.
        """
        token_hash = self.hash_token(raw_token)

        with transaction.atomic():
            current = self.repository.find_for_update_by_hash(token_hash)

            if current is None:
                return None

            was_already_revoked = current.is_revoked
            if not was_already_revoked:
                self.repository.revoke(
                    current,
                    rotated_at=self.clock(),
                )

        return RevokedRefreshToken(
            user=current.user,
            was_already_revoked=was_already_revoked,
        )

    def _issue(
        self,
        *,
        user,
        now: datetime,
        family_id=None,
        parent=None,
        device_info: str = "",
        ip_address: str | None = None,
    ) -> IssuedRefreshToken:
        raw_token = self.token_factory()
        token_hash = self.hash_token(raw_token)
        expires_at = now + settings.AUTH_REFRESH_TOKEN_LIFETIME

        self.repository.create(
            user=user,
            token_hash=token_hash,
            expires_at=expires_at,
            family_id=family_id,
            parent=parent,
            device_info=device_info,
            ip_address=ip_address,
        )

        return IssuedRefreshToken(
            raw_token=raw_token,
            expires_at=expires_at,
            user=user,
        )
