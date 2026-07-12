"""Administrative user-management workflows (CRUD + status transitions).

This service is the single business-logic boundary for superadmin user
administration. Views stay thin and delegate here; data access goes through the
repositories. Keeping it out of the model layer (``account``) preserves the
separation between persistence (models/repositories) and behaviour (services).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from authentication.exceptions import (
    InvalidStatusTransitionError,
    SelfStatusChangeError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)
from authentication.repositories import (
    RefreshTokenRepository,
    UserRepository,
)

# Fields a superadmin may change through the generic update endpoint. Identity
# (username/email) and security state (status/password) are handled by their own
# dedicated flows, not bulk-patched here.
UPDATABLE_FIELDS = ("role", "first_name", "last_name", "organization")


class UserAdminService:
    """Create, read, update, deactivate, and re-status user accounts.

    Status changes are recorded automatically by the User model's history
    (``simple_history``). Activating clears lockout state and re-enables the
    account; suspending or deactivating revokes the user's active refresh tokens
    so existing sessions cannot be silently extended.
    """

    def __init__(
        self,
        *,
        user_repository: UserRepository | None = None,
        refresh_token_repository: RefreshTokenRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.user_repository = user_repository or UserRepository()
        self.refresh_token_repository = (
            refresh_token_repository or RefreshTokenRepository()
        )
        self.clock = clock or timezone.now

    # ----- read ----------------------------------------------------------

    def list_queryset(self):
        return self.user_repository.queryset()

    def get_user(self, user_id):
        user = self.user_repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        return user

    # ----- create --------------------------------------------------------

    def create_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        role: str,
        organization=None,
        first_name: str = "",
        last_name: str = "",
        actor=None,
    ):
        """Provision an immediately-usable, active account."""
        model = self.user_repository.model
        try:
            with transaction.atomic():
                return self.user_repository.create_user(
                    username=username,
                    email=email,
                    password=password,
                    role=role,
                    status=model.Status.ACTIVE,
                    is_active=True,
                    first_name=first_name,
                    last_name=last_name,
                    organization=organization,
                    password_changed_at=self.clock(),
                )
        except IntegrityError as exc:
            raise UsernameAlreadyExistsError() from exc

    # ----- update --------------------------------------------------------

    def update_user(self, *, user_id, data: dict, actor=None):
        model = self.user_repository.model
        with transaction.atomic():
            try:
                user = self.user_repository.get_for_update_by_id(user_id)
            except model.DoesNotExist as exc:
                raise UserNotFoundError() from exc

            update_fields = []
            for field in UPDATABLE_FIELDS:
                if field in data:
                    setattr(user, field, data[field])
                    update_fields.append(field)

            if update_fields:
                self.user_repository.save(user, update_fields=update_fields)
            return user

    # ----- deactivate (soft delete) -------------------------------------

    def deactivate_user(self, *, user_id, actor=None):
        """Soft-delete: suspend, disable, and revoke sessions (reversible)."""
        model = self.user_repository.model
        if actor is not None and str(actor.pk) == str(user_id):
            raise SelfStatusChangeError(
                "You cannot deactivate your own account."
            )

        with transaction.atomic():
            try:
                user = self.user_repository.get_for_update_by_id(user_id)
            except model.DoesNotExist as exc:
                raise UserNotFoundError() from exc

            user.status = model.Status.SUSPENDED
            user.is_active = False
            self.refresh_token_repository.revoke_all_for_user(
                user, rotated_at=self.clock()
            )
            self.user_repository.save(
                user, update_fields=["status", "is_active"]
            )
            return user

    # ----- status transitions -------------------------------------------

    def set_status(self, *, user_id, new_status: str, actor) -> object:
        model = self.user_repository.model
        allowed = {
            model.Status.ACTIVE: {model.Status.INVITED, model.Status.SUSPENDED},
            model.Status.SUSPENDED: {model.Status.ACTIVE, model.Status.INVITED},
        }

        if new_status not in allowed:
            raise InvalidStatusTransitionError(
                f"Status cannot be set to '{new_status}'."
            )

        if actor is not None and str(actor.pk) == str(user_id):
            raise SelfStatusChangeError()

        with transaction.atomic():
            try:
                user = self.user_repository.get_for_update_by_id(user_id)
            except model.DoesNotExist as exc:
                raise UserNotFoundError() from exc

            if user.status not in allowed[new_status]:
                raise InvalidStatusTransitionError(
                    f"Cannot change status from '{user.status}' to "
                    f"'{new_status}'."
                )

            now = self.clock()
            update_fields = ["status"]
            user.status = new_status

            if new_status == model.Status.ACTIVE:
                user.is_active = True
                user.failed_login_count = 0
                user.locked_until = None
                update_fields += [
                    "is_active",
                    "failed_login_count",
                    "locked_until",
                ]
            elif new_status == model.Status.SUSPENDED:
                self.refresh_token_repository.revoke_all_for_user(
                    user, rotated_at=now
                )

            self.user_repository.save(user, update_fields=update_fields)
            return user
