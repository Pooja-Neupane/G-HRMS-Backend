"""Request validation for authentication endpoints."""

from django.conf import settings
from django.contrib.auth.password_validation import (
    validate_password as run_password_validators,
)
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from authentication.email_domain import email_domain_is_deliverable
from authentication.repositories import UserRepository
from organizations.models import Organization


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        max_length=128,
        trim_whitespace=False,
        write_only=True,
    )


class SignupSerializer(serializers.Serializer):
    """Validate a self-service registration request.

    Field-level validation rejects duplicate usernames/emails and enforces
    Django's configured password policy. Business creation happens in the
    service layer; this serializer only validates the request shape.
    """

    user_repository = UserRepository()

    username = serializers.CharField(max_length=150, trim_whitespace=True)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        max_length=128,
        trim_whitespace=False,
        write_only=True,
    )
    password_confirm = serializers.CharField(
        max_length=128,
        trim_whitespace=False,
        write_only=True,
    )

    def validate_username(self, value):
        if self.user_repository.exists_by_username(value):
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate_email(self, value):
        if self.user_repository.exists_by_email(value):
            raise serializers.ValidationError("This email is already registered.")
        if settings.AUTH_SIGNUP_VERIFY_EMAIL_DOMAIN and not email_domain_is_deliverable(
            value,
            timeout=settings.AUTH_SIGNUP_EMAIL_DNS_TIMEOUT,
        ):
            raise serializers.ValidationError(
                "This email domain cannot receive mail. "
                "Please check the address and try again."
            )
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "The two password fields do not match."}
            )

        # Build an unsaved user so similarity validators can compare the
        # password against the username and email without touching the database.
        candidate = self.user_repository.model(
            username=attrs["username"],
            email=attrs["email"],
        )
        try:
            run_password_validators(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})

        return attrs


class UserStatusUpdateSerializer(serializers.Serializer):
    """Admin status change. Only `active`/`suspended` may be set explicitly;
    `invited` is reached only through the signup flow."""

    _User = UserRepository.model

    status = serializers.ChoiceField(
        choices=[
            _User.Status.ACTIVE,
            _User.Status.SUSPENDED,
        ]
    )


class AdminUserSerializer(serializers.ModelSerializer):
    """Read representation of a user for the admin endpoints."""

    class Meta:
        model = UserRepository.model
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "status",
            "is_active",
            "organization",
            "mfa_enabled",
            "date_joined",
            "last_login_at",
        ]
        read_only_fields = fields


class AdminUserCreateSerializer(serializers.Serializer):
    """Validate a superadmin-provisioned account (created `active`)."""

    user_repository = UserRepository()

    username = serializers.CharField(max_length=150, trim_whitespace=True)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        max_length=128,
        trim_whitespace=False,
        write_only=True,
    )
    role = serializers.ChoiceField(choices=UserRepository.model.Role.choices)
    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )
    first_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    last_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )

    def validate_username(self, value):
        if self.user_repository.exists_by_username(value):
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate_email(self, value):
        if self.user_repository.exists_by_email(value):
            raise serializers.ValidationError("This email is already registered.")
        return value

    def validate_password(self, value):
        candidate = self.user_repository.model(
            username=self.initial_data.get("username", ""),
            email=self.initial_data.get("email", ""),
        )
        try:
            run_password_validators(value, user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class AdminUserUpdateSerializer(serializers.Serializer):
    """Validate a partial admin update (role/organization/name only).

    Identity (username/email) and security state (status/password) have their
    own dedicated endpoints and are intentionally not editable here.
    """

    role = serializers.ChoiceField(
        choices=UserRepository.model.Role.choices, required=False
    )
    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(),
        required=False,
        allow_null=True,
    )
    first_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True
    )
    last_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True
    )


class SignupVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    otp = serializers.RegexField(
        r"^\d{4,8}$",
        trim_whitespace=True,
        error_messages={"invalid": "Enter the numeric verification code."},
    )


class SignupResendSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class CsrfTokenSerializer(serializers.Serializer):
    csrf_token = serializers.CharField(read_only=True)


class AccessTokenResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField(read_only=True)
    token_type = serializers.CharField(read_only=True)
    expires_in = serializers.IntegerField(read_only=True)


class UserSummarySerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    username = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)


class LoginResponseSerializer(AccessTokenResponseSerializer):
    user = UserSummarySerializer(read_only=True)


class RegisteredUserSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    role = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)


class SignupResponseSerializer(serializers.Serializer):
    user = RegisteredUserSerializer(read_only=True)


class SignupPendingResponseSerializer(serializers.Serializer):
    """Response for the start/resend steps: a code was sent, no account yet."""

    detail = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    expires_in = serializers.IntegerField(read_only=True)
    resend_available_in = serializers.IntegerField(read_only=True)
