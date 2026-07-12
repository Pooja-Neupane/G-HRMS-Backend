"""Request-scoped context and operational HTTP logging for G-HRMS."""

from __future__ import annotations

import ipaddress
import logging
import re
import time
import uuid
from contextvars import ContextVar

from django.conf import settings


request_logger = logging.getLogger("ghrms.request")

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,128}$")
_current_user: ContextVar[object | None] = ContextVar("current_user", default=None)
_current_ip: ContextVar[str | None] = ContextVar("current_ip", default=None)
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_current_user():
    """Return the actor for the current synchronous request, if available."""
    return _current_user.get()


def get_current_ip() -> str | None:
    return _current_ip.get()


def get_request_id() -> str | None:
    return _request_id.get()


def _valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def get_client_ip(request) -> str | None:
    """
    Return the direct client IP, or the first forwarded IP from a trusted proxy.

    X-Forwarded-For is attacker-controlled unless the direct peer is a proxy we
    explicitly trust, so it is ignored for all other requests.
    """
    remote_addr = _valid_ip(request.META.get("REMOTE_ADDR"))
    trusted_proxies = set(getattr(settings, "TRUSTED_PROXY_IPS", ()))

    if remote_addr in trusted_proxies:
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        forwarded_ip = _valid_ip(forwarded_for.split(",", 1)[0])
        if forwarded_ip:
            return forwarded_ip

    return remote_addr


def _resolve_request_id(request) -> str:
    supplied = request.META.get("HTTP_X_REQUEST_ID", "").strip()
    if _REQUEST_ID_PATTERN.fullmatch(supplied):
        return supplied
    return uuid.uuid4().hex


class RequestContextMiddleware:
    """Attach a correlation ID and emit one privacy-safe access log per request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = _resolve_request_id(request)
        request.request_id = request_id
        request_id_token = _request_id.set(request_id)
        started_at = time.monotonic()
        response = None

        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            return response
        finally:
            if response is not None:
                self._log_response(request, response, started_at)
            _request_id.reset(request_id_token)

    @staticmethod
    def _log_response(request, response, started_at):
        status_code = response.status_code
        if status_code >= 500:
            log_method = request_logger.error
        elif status_code >= 400:
            log_method = request_logger.warning
        else:
            log_method = request_logger.info

        user = getattr(request, "user", None)
        user_id = None
        if user is not None and getattr(user, "is_authenticated", False):
            user_id = str(user.pk)

        log_method(
            "request.completed",
            extra={
                "http_method": request.method,
                "path": request.path,
                "status_code": status_code,
                "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
                "user_id": user_id,
                "client_ip": get_client_ip(request),
            },
        )


class CurrentUserMiddleware:
    """Expose the session-authenticated actor to model audit helpers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_token = _current_user.set(getattr(request, "user", None))
        ip_token = _current_ip.set(get_client_ip(request))
        try:
            return self.get_response(request)
        finally:
            _current_user.reset(user_token)
            _current_ip.reset(ip_token)
