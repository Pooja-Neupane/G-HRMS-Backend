"""Consistent, privacy-safe exception responses for the G-HRMS API."""

from __future__ import annotations

import logging

from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from core.middleware import get_request_id
from core.errors import ApplicationError


logger = logging.getLogger("ghrms.api")

_DEFAULT_ERROR_CODES = {
    400: "bad_request",
    401: "not_authenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    415: "unsupported_media_type",
    429: "throttled",
}


def _normalise_details(value):
    """Convert DRF ErrorDetail objects into JSON-safe message/code objects."""
    if isinstance(value, dict):
        return {key: _normalise_details(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalise_details(item) for item in value]

    code = getattr(value, "code", None)
    if code:
        return {"message": str(value), "code": code}
    return value


def _simple_error_code(exc, status_code):
    if isinstance(exc, APIException):
        codes = exc.get_codes()
        if isinstance(codes, str):
            return codes
    return _DEFAULT_ERROR_CODES.get(status_code, "api_error")


def _simple_message(response_data, status_code):
    if isinstance(response_data, dict) and "detail" in response_data:
        return str(response_data["detail"])
    return {
        400: "The request could not be processed.",
        401: "Authentication credentials were not accepted.",
        403: "You do not have permission to perform this action.",
        404: "The requested resource was not found.",
        405: "This HTTP method is not allowed.",
        429: "Too many requests. Please try again later.",
    }.get(status_code, "The request failed.")


def api_exception_handler(exc, context):
    """Return a stable error envelope for handled and unexpected API errors."""
    request = context.get("request")
    request_id = getattr(request, "request_id", None) or get_request_id()

    if isinstance(exc,ApplicationError):
        return Response(
            {
                "success":False,
                "error":{
                    "code":exc.code,
                    "message":exc.message,
                    "details":(
                        _normalise_details(exc.details)
                        if exc.details is not None
                        else None
                    ),
                },
                "request_id":request_id
            },
            status=exc.status_code,

        )
        
    response = drf_exception_handler(exc, context)

    if response is None:
        logger.exception(
            "api.unhandled_exception",
            exc_info=(type(exc), exc, exc.__traceback__),
            extra={
                "http_method": getattr(request, "method", None),
                "path": getattr(request, "path", None),
                "view": type(context["view"]).__name__ if context.get("view") else None,
            },
        )
        return Response(
            {
                "success": False,
                "error": {
                    "code": "internal_server_error",
                    "message": "An unexpected error occurred.",
                    "details": None,
                },
                "request_id": request_id,
            },
            status=500,
        )

    if isinstance(exc, ValidationError):
        error_code = "validation_error"
        message = "Request validation failed."
        details = _normalise_details(response.data)
    else:
        error_code = _simple_error_code(exc, response.status_code)
        message = _simple_message(response.data, response.status_code)
        details = None

    response.data = {
        "success": False,
        "error": {
            "code": error_code,
            "message": message,
            "details": details,
        },
        "request_id": request_id,
    }
    return response

