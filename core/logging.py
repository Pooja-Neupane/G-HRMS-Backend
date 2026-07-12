"""Structured logging helpers used by Django's LOGGING configuration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from core.middleware import get_request_id


class RequestContextFilter(logging.Filter):
    """Add the current request ID to every record handled by this filter."""

    def filter(self, record):
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """Render operational logs as one JSON object per line."""

    extra_fields = (
        "request_id",
        "http_method",
        "path",
        "status_code",
        "duration_ms",
        "user_id",
        "client_ip",
        "view",
    )

    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self.extra_fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=True)

