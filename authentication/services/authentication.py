"""Authentication and account-lockout workflows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from account.models import AuthEvent
from authentication.exceptions import (
    AccountInactiveError,
    AccountLockedError,
    InvalidCredentialsError,
)
from authentication.repositories import (
    AuthEventRepository,
    UserRepository,
)
from authentication.services.refresh_tokens import (
    IssuedRefreshToken,
    RefreshTokenService,
)

from authentication.services.access_tokens import (
    PasetoAccessTokenService,
)


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: object
    access_token: str
    refresh_token: IssuedRefreshToken


@dataclass(frozen=True, slots=True)
class RefreshResult:
    access_token: str
    refresh_token: IssuedRefreshToken


class AuthenticationService:
    """Authenticate users and coordinate account security state."""

    def __init__(
        self,
        *,
        user_repository: UserRepository | None = None,
        event_repository: AuthEventRepository | None = None,
        refresh_token_service: RefreshTokenService | None = None,
        access_token_service: PasetoAccessTokenService | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.user_repository = user_repository or UserRepository()
        self.event_repository = event_repository or AuthEventRepository()
        self.refresh_token_service = (
            refresh_token_service or RefreshTokenService()
        )
        self.access_token_service = (
            access_token_service or PasetoAccessTokenService()
        )
        self.clock = clock or timezone.now

    def login(
        self,
        *,
        email: str,
        password: str,
        device_info: str = "",
        ip_address: str | None = None,
    ) -> LoginResult:
        pending_error = None
        result = None

        with transaction.atomic():
            user = self.user_repository.find_for_update_by_email(email)

            if user is None:
                self._consume_password_hash(password)
                raise InvalidCredentialsError()

            now = self.clock()
            password_is_valid = user.check_password(password)

            if user.locked_until and user.locked_until <= now:
                user.locked_until = None
                user.failed_login_count = 0

            if not password_is_valid:
                pending_error = self._handle_failed_login(
                    user=user,
                    now=now,
                    ip_address=ip_address,
                    device_info=device_info,
                )

            elif user.locked_until and user.locked_until > now:
                pending_error = AccountLockedError(
                    details={"locked_until": user.locked_until.isoformat()}
                )

            elif not user.is_active or user.status != user.Status.ACTIVE:
                pending_error = AccountInactiveError()

            else:
                self.user_repository.update_fields(
                    user,
                    failed_login_count=0,
                    locked_until=None,
                    last_login=now,
                    last_login_at=now,
                )

                self.event_repository.create(
                    event_type=AuthEvent.Kind.LOGIN,
                    user=user,
                    ip_address=ip_address,
                    user_agent=device_info,
                    occurred_at=now,
                )

                refresh_token = self.refresh_token_service.issue(
                    user=user,
                    device_info=device_info,
                    ip_address=ip_address,
                )

                access_token = self.access_token_service.issue(user=user)

                result = LoginResult(
                    user=user,
                    access_token=access_token,
                    refresh_token=refresh_token,
                )

        # Failed counters and lockout events must commit before raising.
        if pending_error is not None:
            raise pending_error

        if result is None:
            raise RuntimeError("Login completed without a result.")

        return result

    def _handle_failed_login(
        self,
        *,
        user,
        now: datetime,
        ip_address: str | None,
        device_info: str,
    ):
        if user.locked_until and user.locked_until > now:
            return InvalidCredentialsError()

        user.failed_login_count += 1

        if (
            user.failed_login_count
            >= settings.AUTH_MAX_FAILED_LOGIN_ATTEMPTS
        ):
            user.locked_until = now + settings.AUTH_LOCKOUT_DURATION

            self.user_repository.update_fields(
                user,
                failed_login_count=user.failed_login_count,
                locked_until=user.locked_until,
            )

            self.event_repository.create(
                event_type=AuthEvent.Kind.LOCKOUT,
                user=user,
                ip_address=ip_address,
                user_agent=device_info,
                occurred_at=now,
            )

            return AccountLockedError(
                details={"locked_until": user.locked_until.isoformat()}
            )

        self.user_repository.update_fields(
            user,
            failed_login_count=user.failed_login_count,
            locked_until=user.locked_until,
        )
        return InvalidCredentialsError()

    def refresh(self, *, raw_refresh_token: str) -> RefreshResult:
        refresh_token = self.refresh_token_service.rotate(raw_refresh_token)
        access_token = self.access_token_service.issue(user=refresh_token.user)
        return RefreshResult(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    @transaction.atomic
    def logout(
        self,
        *,
        raw_refresh_token: str,
        device_info: str = "",
        ip_address: str | None = None,
    ) -> bool:
        revoked = self.refresh_token_service.revoke(raw_refresh_token)
        if revoked is None:
            return False

        if not revoked.was_already_revoked:
            self.event_repository.create(
                event_type=AuthEvent.Kind.LOGOUT,
                user=revoked.user,
                ip_address=ip_address,
                user_agent=device_info,
                occurred_at=self.clock(),
            )

        return True

    def _consume_password_hash(self, password: str):
        """
        Perform password hashing work for an unknown username.

        This reduces timing differences between unknown-user and wrong-password
        requests.
        """
        dummy_user = self.user_repository.model()
        dummy_user.set_password(password)
