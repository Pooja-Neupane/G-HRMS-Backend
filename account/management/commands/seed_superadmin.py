"""Idempotently create or update the platform SUPERADMIN account.

Usage:
    # password from .env (SUPERADMIN_PASSWORD) or the environment
    python manage.py seed_superadmin

    # or pass everything explicitly
    python manage.py seed_superadmin \
        --email deulatech@gmail.com --username superadmin --password 'StrongPass@123'

The password is never hard-coded or printed. Running the command again updates
the existing account (role/status/flags and, if provided, the password) instead
of creating a duplicate.
"""

from decouple import config
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

User = get_user_model()


class Command(BaseCommand):
    help = "Create or update the SUPERADMIN account (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default=config("SUPERADMIN_EMAIL", default="deulatech@gmail.com"),
        )
        parser.add_argument(
            "--username",
            default=config("SUPERADMIN_USERNAME", default="superadmin"),
        )
        parser.add_argument(
            "--password",
            default=config("SUPERADMIN_PASSWORD", default=""),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        username = options["username"].strip()
        password = options["password"]

        if not email or not username:
            raise CommandError("Both --email and --username are required.")
        if not password:
            raise CommandError(
                "No password provided. Set SUPERADMIN_PASSWORD in .env / the "
                "environment, or pass --password."
            )

        # Match an existing account by email first, then username, so re-runs
        # update in place instead of colliding on the unique username.
        user = (
            User.objects.filter(email__iexact=email).first()
            or User.objects.filter(username=username).first()
        )
        created = user is None
        if user is None:
            user = User(username=username)

        user.email = email
        user.role = User.Role.SUPERADMIN
        user.status = User.Status.ACTIVE
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.failed_login_count = 0
        user.locked_until = None
        user.set_password(password)
        user.password_changed_at = timezone.now()
        user.save()

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} SUPERADMIN '{user.username}' <{user.email}> "
                f"(status={user.status}, active=True)."
            )
        )
