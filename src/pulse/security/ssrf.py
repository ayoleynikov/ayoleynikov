"""SSRF protection for outbound URL fetches (RSS, webhooks, etc.)."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# Hostnames that must never be fetched by connectors.
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata.google",
    }
)


class SSRFError(ValueError):
    """URL rejected as unsafe for server-side fetch."""

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (ip.version == 4 and ip in ipaddress.ip_network("169.254.0.0/16"))
        or (ip.version == 6 and ip in ipaddress.ip_network("fd00::/8"))
    )


def validate_public_url(
    url: str,
    *,
    resolve_dns: bool = True,
    allow_http: bool = True,
) -> str:
    """Validate that ``url`` is safe for the server to fetch.

    Blocks private/link-local/loopback/metadata addresses and non-http(s) schemes.
    When ``resolve_dns`` is True, resolved A/AAAA records are also checked
    (may be skipped in unit tests that only assert hostname rules).
    """
    raw = (url or "").strip()
    if not raw:
        raise SSRFError("URL must not be empty")

    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise SSRFError(
            f"URL scheme not allowed: {scheme or '(none)'}",
            details={"url": raw},
        )
    if scheme == "http" and not allow_http:
        raise SSRFError("HTTP URLs are disabled; use HTTPS", details={"url": raw})

    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise SSRFError("URL missing hostname", details={"url": raw})
    if host in _BLOCKED_HOSTNAMES or host.endswith(".localhost"):
        raise SSRFError(f"Blocked hostname: {host}", details={"host": host})
    if host.endswith(".internal") or host.endswith(".local"):
        raise SSRFError(f"Blocked internal hostname: {host}", details={"host": host})

    # Literal IP in the URL
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and _is_blocked_ip(ip):
        raise SSRFError(f"Blocked IP address: {host}", details={"host": host})

    if resolve_dns and ip is None:
        try:
            infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise SSRFError(
                f"DNS resolution failed for {host}",
                details={"host": host, "error": str(exc)},
            ) from exc
        for info in infos:
            sockaddr = info[4]
            addr = sockaddr[0]
            try:
                resolved = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if _is_blocked_ip(resolved):
                raise SSRFError(
                    f"Hostname {host} resolves to blocked address {resolved}",
                    details={"host": host, "resolved": str(resolved)},
                )

    return raw
