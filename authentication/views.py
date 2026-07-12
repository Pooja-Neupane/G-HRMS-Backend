"""CSRF-protected authentication API endpoints."""

from django.conf import settings
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from authentication.cookies import clear_refresh_cookie, set_refresh_cookie
from authentication.exceptions import (
    InvalidRefreshTokenError,
    TokenReuseDetectedError,
)
from authentication.permissions import IsSuperAdmin
from authentication.serializers import (
    AccessTokenResponseSerializer,
    AdminUserCreateSerializer,
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    CsrfTokenSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    SignupPendingResponseSerializer,
    SignupResendSerializer,
    SignupResponseSerializer,
    SignupSerializer,
    SignupVerifySerializer,
    UserStatusUpdateSerializer,
)
from authentication.services import (
    AuthenticationService,
    SignupService,
    UserAdminService,
)
from core.middleware import get_client_ip


def _device_info(request) -> str:
    return request.META.get("HTTP_USER_AGENT", "")[:255]


def _token_response(access_token: str) -> dict:
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": int(
            settings.PASETO_ACCESS_TOKEN_LIFETIME.total_seconds()
        ),
    }


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Authentication"],
        summary="Get a CSRF token",
        description=(
            "Returns a CSRF token and sets the `csrftoken` cookie. Send the "
            "token in the `X-CSRFToken` header on all state-changing auth "
            "calls (signup, login, refresh, logout)."
        ),
        responses=CsrfTokenSerializer,
    )
    def get(self, request):
        return Response({"csrf_token": get_token(request)})


class AuthenticationServiceMixin:
    service_class = AuthenticationService

    def get_service(self):
        return self.service_class()


class SignupServiceMixin:
    service_class = SignupService

    def get_service(self):
        return self.service_class()


@method_decorator(csrf_protect, name="dispatch")
class SignupView(SignupServiceMixin, APIView):
    """Start a signup: validate, stash a pending registration, e-mail an OTP.

    No database account is created here. The credentials live only in the cache
    (password already hashed) until the e-mail is verified.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "signup"

    @extend_schema(
        tags=["Authentication"],
        summary="Start signup (send OTP)",
        description=(
            "Validates the request, e-mails a one-time verification code, and "
            "stores the pending registration in the cache with the password "
            "already hashed. **No database account is created yet** — call "
            "`/api/auth/signup/verify/` with the code to finish. Returns "
            "`202 Accepted`."
        ),
        request=SignupSerializer,
        responses={202: SignupPendingResponseSerializer},
        examples=[
            OpenApiExample(
                "Signup request",
                value={
                    "username": "dipesh.deula",
                    "email": "dipesh@example.com",
                    "password": "StrongPassword@123",
                    "password_confirm": "StrongPassword@123",
                },
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = self.get_service().start(
            username=serializer.validated_data["username"],
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
            device_info=_device_info(request),
            ip_address=get_client_ip(request),
        )

        return Response(
            {
                "detail": (
                    "A verification code has been sent to your email. "
                    "Enter it to complete signup."
                ),
                "email": result.email,
                "expires_in": result.expires_in,
                "resend_available_in": result.resend_available_in,
            },
            status=status.HTTP_202_ACCEPTED,
        )


@method_decorator(csrf_protect, name="dispatch")
class SignupVerifyView(SignupServiceMixin, APIView):
    """Verify the OTP and persist the account in the INVITED state."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "signup_verify"

    @extend_schema(
        tags=["Authentication"],
        summary="Verify signup OTP (create account)",
        description=(
            "Verifies the one-time code. On success the account is created in "
            "the `invited` state with the least-privilege `VIEWER` role and "
            "cannot log in until an administrator activates it. Wrong codes are "
            "rate-limited and the pending registration is purged after too many "
            "attempts."
        ),
        request=SignupVerifySerializer,
        responses={201: SignupResponseSerializer},
        examples=[
            OpenApiExample(
                "Verify request",
                value={"email": "dipesh@example.com", "otp": "481091"},
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = SignupVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = self.get_service().verify(
            email=serializer.validated_data["email"],
            otp=serializer.validated_data["otp"],
        )

        user = result.user
        return Response(
            {
                "user": {
                    "id": str(user.pk),
                    "username": user.username,
                    "email": user.email,
                    "role": user.role,
                    "status": user.status,
                }
            },
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_protect, name="dispatch")
class SignupResendView(SignupServiceMixin, APIView):
    """Re-issue a verification code for an in-progress signup."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "signup_resend"

    @extend_schema(
        tags=["Authentication"],
        summary="Resend signup OTP",
        description=(
            "Issues a new verification code for an in-progress signup, subject "
            "to a resend cooldown and a maximum number of resends."
        ),
        request=SignupResendSerializer,
        responses={202: SignupPendingResponseSerializer},
        examples=[
            OpenApiExample(
                "Resend request",
                value={"email": "dipesh@example.com"},
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = SignupResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = self.get_service().resend(
            email=serializer.validated_data["email"],
        )

        return Response(
            {
                "detail": "A new verification code has been sent to your email.",
                "email": result.email,
                "expires_in": result.expires_in,
                "resend_available_in": result.resend_available_in,
            },
            status=status.HTTP_202_ACCEPTED,
        )


@method_decorator(csrf_protect, name="dispatch")
class LoginView(AuthenticationServiceMixin, APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Authentication"],
        summary="Log in (email + password)",
        description=(
            "Authenticates with **email** and password. Returns a short-lived "
            "PASETO `access_token` and sets an HttpOnly, SameSite refresh "
            "cookie. Copy the `access_token` into the **Authorize** dialog to "
            "call protected endpoints. Repeated failures lock the account "
            "temporarily; `invited`/inactive accounts are rejected with "
            "`account_inactive`."
        ),
        request=LoginSerializer,
        responses={200: LoginResponseSerializer},
        examples=[
            OpenApiExample(
                "Login request",
                value={"email": "dipesh@example.com", "password": "StrongPassword@123"},
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = self.get_service().login(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
            device_info=_device_info(request),
            ip_address=get_client_ip(request),
        )

        data = _token_response(result.access_token)
        data["user"] = {
            "id": str(result.user.pk),
            "username": result.user.username,
            "role": result.user.role,
        }
        response = Response(data, status=status.HTTP_200_OK)
        set_refresh_cookie(response, result.refresh_token)
        return response


@method_decorator(csrf_protect, name="dispatch")
class RefreshView(AuthenticationServiceMixin, APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Authentication"],
        summary="Refresh the access token",
        description=(
            "Reads the HttpOnly refresh cookie, rotates it, and returns a new "
            "`access_token`. Reusing a revoked refresh token revokes the whole "
            "token family and clears the cookie. No request body is needed."
        ),
        request=None,
        responses={200: AccessTokenResponseSerializer},
    )
    def post(self, request):
        raw_refresh_token = request.COOKIES.get(
            settings.AUTH_REFRESH_COOKIE_NAME
        )
        if not raw_refresh_token:
            raise InvalidRefreshTokenError()

        result = self.get_service().refresh(
            raw_refresh_token=raw_refresh_token
        )
        response = Response(
            _token_response(result.access_token),
            status=status.HTTP_200_OK,
        )
        set_refresh_cookie(response, result.refresh_token)
        return response

    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        if isinstance(
            exc,
            (InvalidRefreshTokenError, TokenReuseDetectedError),
        ):
            clear_refresh_cookie(response)
        return response


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(AuthenticationServiceMixin, APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Authentication"],
        summary="Log out",
        description=(
            "Revokes the refresh token from the cookie and clears it. "
            "Idempotent: returns `204` even if no valid cookie is present."
        ),
        request=None,
        responses={204: OpenApiResponse(description="Logged out")},
    )
    def post(self, request):
        raw_refresh_token = request.COOKIES.get(
            settings.AUTH_REFRESH_COOKIE_NAME
        )
        if raw_refresh_token:
            self.get_service().logout(
                raw_refresh_token=raw_refresh_token,
                device_info=_device_info(request),
                ip_address=get_client_ip(request),
            )

        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response


@extend_schema(tags=["Administration"])
class UserAdminViewSet(viewsets.GenericViewSet):
    """Superadmin user management (Bearer-authenticated, no CSRF cookie).

    Thin endpoints that delegate to ``UserAdminService``. Covers list, retrieve,
    create (provisions an active account), partial update (role/org/name),
    soft-delete (deactivate), and status transitions.
    """

    permission_classes = [IsSuperAdmin]
    serializer_class = AdminUserSerializer
    filterset_fields = ["role", "status", "is_active"]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering_fields = ["id", "username", "date_joined", "last_login_at"]
    ordering = ["id"]

    service_class = UserAdminService

    def get_service(self):
        return self.service_class()

    def get_queryset(self):
        return self.get_service().list_queryset()

    @extend_schema(
        summary="List users",
        description="Paginated, filterable (`role`, `status`, `is_active`), "
        "searchable (`username`, `email`, name), orderable.",
        responses=AdminUserSerializer(many=True),
    )
    def list(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = AdminUserSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(summary="Retrieve a user", responses=AdminUserSerializer)
    def retrieve(self, request, pk=None):
        user = self.get_service().get_user(pk)
        return Response(AdminUserSerializer(user).data)

    @extend_schema(
        summary="Create a user (active)",
        description="Provisions an immediately-usable `active` account with the "
        "admin-supplied password.",
        request=AdminUserCreateSerializer,
        responses={201: AdminUserSerializer},
    )
    def create(self, request):
        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = self.get_service().create_user(
            actor=request.user, **serializer.validated_data
        )
        return Response(
            AdminUserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Update a user (role/organization/name)",
        request=AdminUserUpdateSerializer,
        responses=AdminUserSerializer,
    )
    def partial_update(self, request, pk=None):
        serializer = AdminUserUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = self.get_service().update_user(
            user_id=pk,
            data=serializer.validated_data,
            actor=request.user,
        )
        return Response(AdminUserSerializer(user).data)

    @extend_schema(
        summary="Deactivate a user (soft delete)",
        description="Marks the account suspended and inactive and revokes its "
        "sessions. Reversible via the status endpoint.",
        responses={200: AdminUserSerializer},
    )
    def destroy(self, request, pk=None):
        user = self.get_service().deactivate_user(
            user_id=pk, actor=request.user
        )
        return Response(
            AdminUserSerializer(user).data, status=status.HTTP_200_OK
        )

    @extend_schema(
        summary="Set a user's account status",
        description="Transitions between `active`/`suspended` (and from "
        "`invited`). Activating clears lockout and re-enables the account; "
        "suspending revokes sessions. You cannot change your own status.",
        request=UserStatusUpdateSerializer,
        responses=AdminUserSerializer,
        examples=[
            OpenApiExample(
                "Activate an invited user",
                value={"status": "active"},
                request_only=True,
            ),
        ],
    )
    @action(
        detail=True,
        methods=["patch"],
        url_path="status",
        url_name="status",
    )
    def set_status(self, request, pk=None):
        serializer = UserStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = self.get_service().set_status(
            user_id=pk,
            new_status=serializer.validated_data["status"],
            actor=request.user,
        )
        return Response(AdminUserSerializer(user).data)
