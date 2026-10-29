"""Trusted public URL origins and opt-in HTTP-to-HTTPS redirects.

No outgoing requests or implicit trust of Host / X-Forwarded-* headers.
Production external HTTPS is normally terminated at an ingress/load balancer.
Only enable the optional in-app redirect after independently verifying that
the listed immediate proxy peers sanitize X-Forwarded-Proto in staging.
"""
from __future__ import annotations

import logging
import os
import re
from ipaddress import ip_address
from urllib.parse import urlsplit

from app.api.client_ip import _peer_ip, _trusted_proxy_networks

log = logging.getLogger(__name__)
_DNS_LABEL = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
_MAX_REDIRECT_PART = 8192


def trusted_public_origin(raw: str) -> str:
    """Validate a configured origin, never one derived from an HTTP request.

    HTTPS only, except HTTP localhost during explicit TEST_MODE=1.
    No credentials, path (other than /), query, fragment, unicode host,
    encoded authority, whitespace, backslash or ambiguous port.
    """
    if not isinstance(raw, str) or not raw:
        raise ValueError("trusted public origin is not configured")
    if (
        len(raw) > 512 or raw != raw.strip()
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in raw)
        or "\\" in raw
    ):
        raise ValueError("invalid trusted public origin")
    try:
        parts = urlsplit(raw)
        hostname = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise ValueError("invalid public origin URL") from exc

    if (
        parts.scheme not in ("https", "http")
        or not parts.netloc or not hostname
        or "%" in parts.netloc or "@" in parts.netloc
        or parts.username is not None or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query or parts.fragment
    ):
        raise ValueError("invalid trusted public origin URL")
    if not hostname.isascii() or len(hostname) > 253:
        raise ValueError("invalid trusted public origin hostname")
    try:
        ip_address(hostname)
    except ValueError:
        if any(not _DNS_LABEL.fullmatch(label) for label in hostname.split(".")):
            raise ValueError("invalid trusted public origin hostname")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("invalid public origin port")
    if parts.scheme == "http" and not (
        os.getenv("TEST_MODE") == "1" and hostname in ("localhost", "127.0.0.1", "::1")
    ):
        raise ValueError("public origin must use HTTPS")

    authority = hostname.lower()
    if ":" in authority:
        authority = f"[{authority}]"
    if port is not None:
        authority += f":{port}"
    return f"{parts.scheme}://{authority}"


def configured_oauth_origin() -> str:
    """Only explicit OAuth/public configuration may set provider redirect_uri."""
    raw = (
        os.getenv("OAUTH_REDIRECT_BASE_URL") or os.getenv("APP_BASE_URL") or ""
    )
    return trusted_public_origin(raw)


def _single_header(request, name: str) -> str | None:
    headers = request.headers.getlist(name)
    return headers[0] if len(headers) == 1 else None


def _validated_request_suffix(request) -> str | None:
    """Use ASGI path/query, never URL authority, to build a safe redirect."""
    raw_path = request.scope.get("raw_path")
    if raw_path is None:
        from urllib.parse import quote
        raw_path = quote(request.scope.get("path", "/"), safe="/%-._~").encode("ascii")
    raw_query = request.scope.get("query_string", b"")
    if not isinstance(raw_path, bytes) or not isinstance(raw_query, bytes):
        return None
    if (
        not raw_path.startswith(b"/") or raw_path.startswith(b"//")
        or any(len(part) > _MAX_REDIRECT_PART or any(
            code < 32 or code == 127 for code in part
        ) for part in (raw_path, raw_query))
        or b"#" in raw_path or b"?" in raw_path or b"\\" in raw_path
        or b"#" in raw_query or b"\\" in raw_query
    ):
        return None
    try:
        path = raw_path.decode("ascii")
        query = raw_query.decode("ascii")
    except UnicodeDecodeError:
        return None
    return path + (("?" + query) if query else "")


def trusted_https_redirect_target(request) -> str | None:
    """Return a canonical redirect only for an explicitly trusted HTTP hop.

    Feature is OFF by default. Both the immediate socket peer and Host must
    match the configured trust boundary. No X-Forwarded-Host, no request.url.
    A proxy must overwrite/sanitize X-Forwarded-Proto before enabling this.
    """
    if os.getenv("HTTPS_REDIRECT_ENABLED") != "1":
        return None
    if request.url.path == "/health":
        return None

    try:
        proxy_ranges = _trusted_proxy_networks(
            os.getenv("HTTPS_REDIRECT_TRUSTED_PROXY_CIDRS", "")
        )
        if not proxy_ranges:
            return None
        peer = ip_address(_peer_ip(request))
        if not any(peer in network for network in proxy_ranges):
            return None
        base = trusted_public_origin(os.getenv("APP_BASE_URL", ""))
        if not base.startswith("https://"):
            return None
    except ValueError:
        log.error("https_redirect_trust_config_invalid_or_unavailable")
        return None

    # Refuse duplicate/ambiguous forwarded-proto and Host headers.
    proto = _single_header(request, "x-forwarded-proto")
    host = _single_header(request, "host")
    if proto != "http" or not host:
        return None
    expected_authority = base.split("://", 1)[1]
    if host.casefold() != expected_authority.casefold():
        return None

    suffix = _validated_request_suffix(request)
    if suffix is None:
        return None
    return base + suffix
