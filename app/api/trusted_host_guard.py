"""Opt-in, fail-closed HTTP Host allowlist for Bridge Hub (Chat174).

Disabled by default to avoid breaking unverified Cloud Run/custom-domain ingress.
Explicitly opt in ONLY after isolated staging has inventoried every authorized
Host, port, OAuth callback and probe. Ignores X-Forwarded-Host entirely.
Do not assume the public Host matches APP_BASE_URL for every internal route.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.trusted_request_origin import trusted_public_origin

log = logging.getLogger(__name__)
_MAX_HOSTS = 32
_MAX_ALLOWLIST_LENGTH = 2048
_MAX_HOST_HEADER_LENGTH = 255


def _canonical_authority(host: str) -> str:
    """Accept only strict ASCII host[:port] or bracketed IPv6[:port].

    Reject wildcard, scheme, URL userinfo/path/query/fragment, encoded
    authority, control characters and ambiguous port syntax. Normalize only
    letter case, never silently remove or reinterpret a port.
    """
    if not isinstance(host, str) or not host or len(host) > _MAX_HOST_HEADER_LENGTH:
        raise ValueError("invalid Host authority")
    if host != host.strip() or "*" in host or any(
        ord(char) < 33 or ord(char) > 126 for char in host
    ):
        raise ValueError("invalid Host authority")
    canonical = trusted_public_origin("https://" + host).split("://", 1)[1]
    if canonical != host.lower():
        raise ValueError("noncanonical Host authority")
    return canonical


@lru_cache(maxsize=32)
def _parse_explicit_hosts(raw: str) -> frozenset[str]:
    if not isinstance(raw, str) or not raw or len(raw) > _MAX_ALLOWLIST_LENGTH:
        raise ValueError("explicit Host allowlist required")
    parts = raw.split(",")
    if len(parts) > _MAX_HOSTS or not all(parts):
        raise ValueError("invalid Host allowlist")
    allowed = frozenset(_canonical_authority(item) for item in parts)
    if len(allowed) != len(parts):
        raise ValueError("duplicate Host allowlist entry")
    return allowed


def _request_authority(request: Request) -> str:
    # Read raw ASGI headers. Do not rely on request.url (may be derived from
    # the very Host header we are checking) or any forwarded Host headers.
    values = []
    for name, value in request.scope.get("headers", []):
        if name.lower() == b"host":
            values.append(value)
    if len(values) != 1:
        raise ValueError("exactly one Host required")
    try:
        decoded = values[0].decode("ascii")
    except (UnicodeDecodeError, AttributeError) as exc:
        raise ValueError("non-ASCII Host") from exc
    return _canonical_authority(decoded)


def trusted_host_decision(request: Request) -> tuple[bool, int, str]:
    """Return allowed/status/code without revealing untrusted Host in logs."""
    setting = os.getenv("BRIDGE_TRUSTED_HOSTS_ENFORCE", "")
    if setting in ("", "0"):
        return True, 200, ""
    if setting != "1":
        # A misspelled activation flag must not silently deactivate protection.
        log.error("trusted_host_enforcement_flag_invalid")
        return False, 503, "HOST_POLICY_UNAVAILABLE"

    try:
        allowed = _parse_explicit_hosts(os.getenv("BRIDGE_TRUSTED_HOSTS", ""))
    except ValueError:
        log.error("trusted_host_allowlist_unavailable")
        return False, 503, "HOST_POLICY_UNAVAILABLE"

    try:
        host = _request_authority(request)
    except ValueError:
        return False, 400, "HOST_UNTRUSTED"
    if host not in allowed:
        return False, 400, "HOST_UNTRUSTED"
    return True, 200, ""


async def trusted_host_guard_middleware(request: Request, call_next):
    """Global ASGI HTTP guard, registered outermost in main.py."""
    allowed, status, code = trusted_host_decision(request)
    if allowed:
        return await call_next(request)
    result = JSONResponse(
        status_code=status,
        content={
            "ok": False,
            "message": "Request host not permitted"
            if status == 400 else "Service temporarily unavailable",
            "data": None,
            "error": {"code": code, "details": None},
        },
    )
    result.headers["Cache-Control"] = "no-store"
    return result
