"""DRF authentication backed by PASETO v4.public access tokens.

Clients send ``Authorization: Bearer <access_token>`` where the token is the
``access_token`` returned by ``/api/auth/login/``. This authenticator is a
*default* authenticator: a request without a Bearer header is simply treated as
anonymous (it returns ``None``) so currently-public endpoints keep working.
Authorization (RBAC) is enforced separately by permissions.
"""

from __future__ import annotations

from functools import lru_cache

from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

from authentication.exceptions import InvalidAccessTokenError
from authentication.services.access_tokens import PasetoAccessTokenService

User = get_user_model()


@lru_cache(maxsize=1)
def _default_token_service() -> PasetoAccessTokenService:
    """Build the token service once; it reads key files at construction."""
    return PasetoAccessTokenService()


class PasetoAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    # Overridable in tests to avoid the cached, key-reading singleton.
    token_service: PasetoAccessTokenService | None = None

    def _service(self) -> PasetoAccessTokenService:
        return self.token_service or _default_token_service()

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()

        if not header or header[0].lower() != self.keyword.lower().encode():
            # No Bearer credentials: let the request proceed as anonymous.
            return None

        if len(header) == 1:
            raise exceptions.AuthenticationFailed(
                "Invalid bearer header: no credentials provided."
            )
        if len(header) > 2:
            raise exceptions.AuthenticationFailed(
                "Invalid bearer header: token must not contain spaces."
            )

        try:
            raw_token = header[1].decode("utf-8")
        except UnicodeError:
            raise exceptions.AuthenticationFailed(
                "Invalid bearer header: token is not valid UTF-8."
            )

        try:
            claims = self._service().verify(raw_token)
        except InvalidAccessTokenError:
            raise exceptions.AuthenticationFailed(
                "The access token is invalid or expired."
            )

        user = self._resolve_user(claims)
        return (user, claims)

    def _resolve_user(self, claims):
        user = User.objects.filter(pk=claims.user_id).first()
        if user is None:
            raise exceptions.AuthenticationFailed(
                "No active account matches this token."
            )
        if not user.is_active or user.status != User.Status.ACTIVE:
            raise exceptions.AuthenticationFailed(
                "This account is no longer active."
            )
        return user

    def authenticate_header(self, request):
        # Makes DRF return 401 (not 403) and advertise the scheme via WWW-Authenticate.
        return self.keyword
