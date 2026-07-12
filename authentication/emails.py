"""Transactional emails for the authentication application."""

from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail


def send_signup_otp_email(
    *,
    email: str,
    otp: str,
    username: str = "",
    expires_in_minutes: int = 10,
) -> None:
    """Send a signup verification code to a prospective user.

    The message is intentionally plain text: it is the most deliverable format
    through restrictive government mail gateways and avoids leaking the code
    into HTML-rendering preview panes. The OTP is never logged.
    """
    greeting = f"Hello {username}," if username else "Hello,"
    subject = "Your G-HRMS verification code"
    message = (
        f"{greeting}\n\n"
        "Use the verification code below to complete your G-HRMS sign-up:\n\n"
        f"    {otp}\n\n"
        f"This code expires in {expires_in_minutes} minutes. "
        "Do not share it with anyone.\n\n"
        "If you did not request this, you can safely ignore this email; "
        "no account will be created.\n\n"
        "— G-HRMS"
    )

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
