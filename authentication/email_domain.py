"""Best-effort email-domain deliverability check for signup.

This is an anti-abuse heuristic, NOT a security boundary: it rejects e-mail
addresses whose domain clearly cannot receive mail (typos, throwaway domains)
before an OTP is generated or an SMTP message is sent. The OTP itself remains
the actual proof that the address is real and reachable.

The check is deliberately fail-open: if DNS is slow, blocked, or unavailable
(common on locked-down government networks) the signup is allowed through and a
warning is logged, so a flaky resolver never locks out legitimate users.
"""

from __future__ import annotations

import logging

import dns.resolver
from dns.exception import DNSException

logger = logging.getLogger("ghrms.api")


def email_domain_is_deliverable(email: str, *, timeout: float = 3.0) -> bool:
    """Return True if the address's domain can plausibly receive mail.

    Returns ``False`` only when the domain authoritatively does not exist or has
    no MX and no A/AAAA records. Any DNS error or timeout returns ``True``
    (fail-open).
    """
    domain = email.rsplit("@", 1)[-1].strip().rstrip(".").lower()
    if not domain:
        return False

    resolver = dns.resolver.Resolver()
    resolver.timeout = timeout
    resolver.lifetime = timeout

    try:
        # A domain with MX records accepts mail directly.
        try:
            if resolver.resolve(domain, "MX"):
                return True
        except dns.resolver.NoAnswer:
            pass

        # RFC 5321: with no MX, a domain still accepts mail at its A/AAAA host.
        for record_type in ("A", "AAAA"):
            try:
                if resolver.resolve(domain, record_type):
                    return True
            except dns.resolver.NoAnswer:
                continue

        # Domain resolves but advertises no way to receive mail.
        return False
    except dns.resolver.NXDOMAIN:
        # The domain does not exist at all.
        return False
    except (DNSException, OSError) as exc:
        logger.warning(
            "signup.email_domain_check_unavailable",
            extra={"reason": type(exc).__name__},
        )
        return True
