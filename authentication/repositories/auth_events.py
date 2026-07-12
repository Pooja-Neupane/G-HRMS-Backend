"""Persistence operations for authentication security events."""

from datetime import datetime

from account.models import AuthEvent


class AuthEventRepository:
    """Persist immutable authentication and security events."""

    model = AuthEvent

    def create(
        self,
        *,
        event_type: str,
        user=None,
        ip_address: str | None = None,
        user_agent: str = "",
        occurred_at: datetime | None = None,
    ):
        values = {
            "event_type": event_type,
            "user": user,
            "ip_address": ip_address,
            "user_agent": user_agent,
        }

        if occurred_at is not None:
            values["occurred_at"] = occurred_at

        return self.model.objects.create(**values)