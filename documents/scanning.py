"""Malware scanning backends for uploaded document versions.

The concrete backend talks to a ClamAV ``clamd`` daemon over a Unix socket or
TCP. ``clamd`` is imported lazily so the project runs without the dependency
installed until scanning is actually enabled.
"""

import logging
from dataclasses import dataclass

from django.conf import settings

from documents.models import DocumentVersion


logger = logging.getLogger("ghrms.documents.scanning")


@dataclass(frozen=True)
class ScanOutcome:
    """Result of inspecting one file, mapped to a DocumentVersion.ScanStatus."""

    status: str
    signature: str = ""
    detail: str = ""


class ClamAVScanner:
    """Streams file content to a clamd daemon and maps the verdict."""

    def __init__(self, *, host, port, timeout, unix_socket=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.unix_socket = unix_socket

    def _client(self):
        import clamd

        if self.unix_socket:
            return clamd.ClamdUnixSocket(
                path=self.unix_socket, timeout=self.timeout
            )
        return clamd.ClamdNetworkSocket(
            host=self.host, port=self.port, timeout=self.timeout
        )

    def scan(self, fileobj):
        """Inspect a readable, binary file object and return a ScanOutcome.

        Any transport or daemon error is reported as FAILED rather than raised,
        so an unreachable scanner never blocks the surrounding workflow; the
        version simply stays unverifiable until a successful re-scan.
        """
        try:
            response = self._client().instream(fileobj)
        except Exception as exc:  # noqa: BLE001 - any clamd/socket failure
            logger.warning(
                "clamav.scan_failed",
                extra={"error": str(exc)},
            )
            return ScanOutcome(
                DocumentVersion.ScanStatus.FAILED, detail=str(exc)
            )

        status, signature = response.get("stream", ("ERROR", None))
        if status == "OK":
            return ScanOutcome(DocumentVersion.ScanStatus.CLEAN)
        if status == "FOUND":
            logger.warning(
                "clamav.infected", extra={"signature": signature}
            )
            return ScanOutcome(
                DocumentVersion.ScanStatus.INFECTED,
                signature=signature or "",
            )
        return ScanOutcome(
            DocumentVersion.ScanStatus.FAILED,
            detail=str(status),
        )


def get_scanner():
    """Return the configured scanner, or None when scanning is disabled."""
    if not getattr(settings, "DOCUMENT_SCAN_ENABLED", False):
        return None
    return ClamAVScanner(
        host=settings.CLAMAV_HOST,
        port=settings.CLAMAV_PORT,
        timeout=settings.CLAMAV_TIMEOUT,
        unix_socket=settings.CLAMAV_UNIX_SOCKET or None,
    )
