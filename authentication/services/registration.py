"""Pending-registration and signup OTP workflow.

Credentials submitted at sign-up are NOT written to the database. They are held
in the cache (Redis in production) with the password already hashed, keyed by
the e-mail address, and only persisted to the database once the user proves
ownership of that e-mail by returning the one-time code. Until then nothing
about the account exists in the database, so an unverified e-mail can never
occupy a username or leave a half-created row behind.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.cache import caches
from django.db import IntegrityError, transaction
from django.utils import timezone

from authentication.emails import send_signup_otp_email
from authentication.exceptions import (
    InvalidOtpError,
    OtpResendThrottledError,
    PendingRegistrationNotFoundError,
    TooManyOtpAttemptsError,
    UsernameAlreadyExistsError,
)
from authentication.repositories import UserRepository


@dataclass(frozen=True, slots=True)
class StartedRegistration:
    """Result of starting or resending a signup (no account exists yet)."""

    email: str
    expires_in: int
    resend_available_in: int


@dataclass(frozen=True, slots=True)
class VerifiedRegistration:
    user: object


class SignupService:
    """Coordinate the cached, OTP-gated self-service registration flow."""

    def __init__(
        self,
        *,
        user_repository: UserRepository | None = None,
        cache=None,
        otp_email_sender: Callable[..., None] | None = None,
        clock: Callable[[], datetime] | None = None,
        otp_factory: Callable[[], str] | None = None,
    ):
        self.user_repository = user_repository or UserRepository()
        self.cache = cache if cache is not None else caches["default"]
        self.send_otp_email = otp_email_sender or send_signup_otp_email
        self.clock = clock or timezone.now
        self.otp_factory = otp_factory or self._generate_otp

    # ----- public API ----------------------------------------------------

    def start(
        self,
        *,
        username: str,
        email: str,
        password: str,
        device_info: str = "",
        ip_address: str | None = None,
    ) -> StartedRegistration:
        """Stash a pending registration and e-mail a fresh code.

        Any earlier pending registration for the same e-mail is replaced. The
        plaintext password is hashed immediately and never stored.
        """
        email = self._normalise_email(email)
        now = self.clock()
        otp = self.otp_factory()
        expires_at = now + settings.AUTH_SIGNUP_OTP_TTL

        record = {
            "username": username,
            "email": email,
            "password_hash": make_password(password),
            "otp_hash": self._hash_otp(otp),
            "attempts": 0,
            "resend_count": 0,
            "created_at": now.isoformat(),
            "last_sent_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        self._store(record, now)
        self._deliver(record, otp)
        return self._started(email)

    def verify(self, *, email: str, otp: str) -> VerifiedRegistration:
        """Validate the code and persist the account on success."""
        email = self._normalise_email(email)
        key = self._cache_key(email)
        record = self.cache.get(key)
        if record is None:
            raise PendingRegistrationNotFoundError()

        if record["attempts"] >= settings.AUTH_SIGNUP_OTP_MAX_ATTEMPTS:
            self.cache.delete(key)
            raise TooManyOtpAttemptsError()

        if not hmac.compare_digest(record["otp_hash"], self._hash_otp(otp)):
            record["attempts"] += 1
            if record["attempts"] >= settings.AUTH_SIGNUP_OTP_MAX_ATTEMPTS:
                self.cache.delete(key)
                raise TooManyOtpAttemptsError()
            self._store(record, self.clock())
            raise InvalidOtpError()

        user = self._persist(record)
        self.cache.delete(key)
        return VerifiedRegistration(user=user)

    def resend(self, *, email: str) -> StartedRegistration:
        """Issue a new code for an existing pending registration."""
        email = self._normalise_email(email)
        key = self._cache_key(email)
        record = self.cache.get(key)
        if record is None:
            raise PendingRegistrationNotFoundError()

        now = self.clock()
        last_sent = datetime.fromisoformat(record["last_sent_at"])
        cooldown = settings.AUTH_SIGNUP_OTP_RESEND_COOLDOWN.total_seconds()
        elapsed = (now - last_sent).total_seconds()
        if elapsed < cooldown:
            raise OtpResendThrottledError(
                details={"retry_after": int(cooldown - elapsed)}
            )

        if record["resend_count"] >= settings.AUTH_SIGNUP_OTP_MAX_RESENDS:
            raise OtpResendThrottledError(
                message=(
                    "The maximum number of verification codes has been "
                    "reached. Please sign up again."
                )
            )

        otp = self.otp_factory()
        record["otp_hash"] = self._hash_otp(otp)
        record["attempts"] = 0
        record["resend_count"] += 1
        record["last_sent_at"] = now.isoformat()
        record["expires_at"] = (
            now + settings.AUTH_SIGNUP_OTP_TTL
        ).isoformat()
        self._store(record, now)
        self._deliver(record, otp)
        return self._started(email)

    # ----- internals -----------------------------------------------------

    def _persist(self, record: dict):
        model = self.user_repository.model
        try:
            with transaction.atomic():
                return self.user_repository.create_with_password_hash(
                    username=record["username"],
                    email=record["email"],
                    password_hash=record["password_hash"],
                    role=model.Role.VIEWER,
                    status=model.Status.INVITED,
                    password_changed_at=self.clock(),
                )
        except IntegrityError as exc:
            # The username was taken by someone else while this registration
            # was pending; the database unique constraint is the final guard.
            self.cache.delete(self._cache_key(record["email"]))
            raise UsernameAlreadyExistsError() from exc

    def _deliver(self, record: dict, otp: str) -> None:
        self.send_otp_email(
            email=record["email"],
            otp=otp,
            username=record["username"],
            expires_in_minutes=int(
                settings.AUTH_SIGNUP_OTP_TTL.total_seconds() // 60
            ),
        )

    def _store(self, record: dict, now: datetime) -> None:
        expires_at = datetime.fromisoformat(record["expires_at"])
        timeout = max(1, int((expires_at - now).total_seconds()))
        self.cache.set(self._cache_key(record["email"]), record, timeout=timeout)

    def _started(self, email: str) -> StartedRegistration:
        return StartedRegistration(
            email=email,
            expires_in=int(settings.AUTH_SIGNUP_OTP_TTL.total_seconds()),
            resend_available_in=int(
                settings.AUTH_SIGNUP_OTP_RESEND_COOLDOWN.total_seconds()
            ),
        )

    def _cache_key(self, email: str) -> str:
        digest = hashlib.sha256(email.encode("utf-8")).hexdigest()
        return f"{settings.AUTH_SIGNUP_CACHE_PREFIX}:{digest}"

    def _normalise_email(self, email: str) -> str:
        manager = self.user_repository.model._default_manager
        return manager.normalize_email(email).strip().lower()

    @staticmethod
    def _hash_otp(otp: str) -> str:
        return hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            otp.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _generate_otp() -> str:
        length = settings.AUTH_SIGNUP_OTP_LENGTH
        return "".join(secrets.choice("0123456789") for _ in range(length))
