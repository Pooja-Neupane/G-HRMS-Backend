"""Persistence operations for authentication users."""

from collections.abc import Iterable

from django.contrib.auth import get_user_model

User = get_user_model()

class UserRepository:
    """Isolate user queries required by authentication workflows."""

    model = User

    def find_by_login(self,login:str):
        """Return a user by Django's configured login field."""
        login_field = self.model.USERNAME_FIELD

        return (
            self.model._default_manager
            .filter(**{login_field:login}).first()
        )

    def exists_by_username(self, username: str) -> bool:
        """Return True if a user already uses this username (case-insensitive)."""
        return (
            self.model._default_manager
            .filter(username__iexact=username)
            .exists()
        )

    def exists_by_email(self, email: str) -> bool:
        """Return True if a user already uses this email (case-insensitive)."""
        if not email:
            return False
        return (
            self.model._default_manager
            .filter(email__iexact=email)
            .exists()
        )

    def queryset(self):
        """Base queryset for admin listing.

        The organization FK is serialized by primary key (DRF's PK-only
        optimisation reads ``organization_id`` directly), so no join to the
        organizations table is needed here.
        """
        return self.model._default_manager.all()

    def get_by_id(self, user_id):
        """Return a single user by primary key, or None."""
        return (
            self.model._default_manager
            .filter(pk=user_id)
            .first()
        )

    def create_user(self, *, username: str, email: str, password: str, **extra_fields):
        """Create a user from a raw password (admin provisioning).

        Delegates to Django's ``UserManager.create_user`` so the password is
        hashed and the email normalised consistently. Distinct from
        ``create_with_password_hash`` used by the OTP flow, which receives an
        already-hashed password.
        """
        return self.model._default_manager.create_user(
            username=username,
            email=email,
            password=password,
            **extra_fields,
        )

    def create_with_password_hash(
        self,
        *,
        username: str,
        email: str,
        password_hash: str,
        **extra_fields,
    ):
        """Create a user from an already-hashed password.

        The signup OTP flow hashes the password before caching the pending
        registration and discards the plaintext immediately, so by the time the
        account is persisted there is no raw password to hash again. The stored
        Argon2 hash is assigned directly; Django's ``check_password`` reads it
        the same way it would a hash produced by ``set_password``.
        """
        manager = self.model._default_manager
        user = self.model(
            username=username,
            email=manager.normalize_email(email),
            **extra_fields,
        )
        user.password = password_hash
        user.save(using=manager.db)
        return user
    
    def find_for_update_by_login(self,login:str):
        """Return and lock a user for an authentication transaction.
           This must be called inside transaction.atomic().
        """

        login_field = self.model.USERNAME_FIELD

        return(
            self.model._default_manager
            .select_for_update()
            .filter(**{login_field:login})
            .first()
        )
    
    def find_for_update_by_email(self, email: str):
        """Return and lock a user by email (case-insensitive).

        Login uses the email address as the identifier. Email uniqueness is
        enforced when accounts are created; ``first()`` keeps a defensive guard
        against any historical duplicate. Must be called inside
        ``transaction.atomic()``.
        """
        return (
            self.model._default_manager
            .select_for_update()
            .filter(email__iexact=email)
            .order_by("pk")
            .first()
        )

    def get_for_update_by_id(self,user_id):
        """
            Return and lock a user by primary key.
            This must be called inside transaction.atomic().
        """

        return(
            self.model._default_manager.
            select_for_update()
            .get(pk=user_id)
        )
    
    @staticmethod
    def save(user,*,update_fields:Iterable[str] | None = None):
        """Persist a user through one explicit repository boundary."""
        fields = list(dict.fromkeys(update_fields)) if update_fields else None
        user.save(update_fields = fields)
        return user

    def update_fields(self, user, **values):
        """Update selected columns without triggering model save signals.

        Login and lockout bookkeeping only needs to persist operational fields;
        using ``QuerySet.update()`` avoids model-level history hooks on every
        authentication attempt while keeping the in-memory instance in sync.
        """
        if not values:
            return user

        self.model._default_manager.filter(pk=user.pk).update(**values)
        for field, value in values.items():
            setattr(user, field, value)
        return user
