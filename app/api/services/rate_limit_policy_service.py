"""app/api/services/rate_limit_policy_service.py

Pure rate-limit policy classification and decision logic.
No Redis calls, no DB, no network — safe to import anywhere including tests.

Categories → rules → key builder → error builder.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Category constants
# ---------------------------------------------------------------------------

class RateLimitCategory:
    SAFE            = "safe"
    AUTH            = "auth"
    CREDENTIAL      = "credential"
    CONNECTOR       = "connector"
    POSTING         = "posting"
    AI_HEAVY        = "ai_heavy"
    DOCUMENT_UPLOAD = "document_upload"
    ADMIN           = "admin"
    DEFAULT         = "default"


# Error codes per category — align with contract test REQUIRED_ERROR_CODES
_CATEGORY_ERROR_CODE: dict[str, str] = {
    RateLimitCategory.AUTH:            "AUTH_RATE_LIMIT_EXCEEDED",
    RateLimitCategory.CREDENTIAL:      "CREDENTIAL_RATE_LIMIT_EXCEEDED",
    RateLimitCategory.CONNECTOR:       "CONNECTOR_RATE_LIMIT_EXCEEDED",
    RateLimitCategory.POSTING:         "CONNECTOR_RATE_LIMIT_EXCEEDED",
    RateLimitCategory.AI_HEAVY:        "AI_RATE_LIMIT_EXCEEDED",
    RateLimitCategory.DOCUMENT_UPLOAD: "RATE_LIMIT_EXCEEDED",
    RateLimitCategory.ADMIN:           "RATE_LIMIT_EXCEEDED",
    RateLimitCategory.DEFAULT:         "RATE_LIMIT_EXCEEDED",
    RateLimitCategory.SAFE:            "RATE_LIMIT_EXCEEDED",
}

# Categories that are actively rate-limited (not safe)
_RATE_LIMITED_CATEGORIES: frozenset[str] = frozenset({
    RateLimitCategory.AUTH,
    RateLimitCategory.CREDENTIAL,
    RateLimitCategory.CONNECTOR,
    RateLimitCategory.POSTING,
    RateLimitCategory.AI_HEAVY,
    RateLimitCategory.DOCUMENT_UPLOAD,
    RateLimitCategory.ADMIN,
    RateLimitCategory.DEFAULT,
})


# ---------------------------------------------------------------------------
# Rule dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RateLimitRule:
    """Immutable rate-limit policy rule for a category."""
    category: str
    limit: int           # max requests in window
    window_seconds: int  # window duration
    error_code: str


# ---------------------------------------------------------------------------
# Default rules — one per category
# ---------------------------------------------------------------------------

_RULES: dict[str, RateLimitRule] = {
    RateLimitCategory.SAFE: RateLimitRule(
        category=RateLimitCategory.SAFE,
        limit=10_000,
        window_seconds=60,
        error_code="RATE_LIMIT_EXCEEDED",
    ),
    RateLimitCategory.AUTH: RateLimitRule(
        category=RateLimitCategory.AUTH,
        limit=10,
        window_seconds=60,
        error_code="AUTH_RATE_LIMIT_EXCEEDED",
    ),
    RateLimitCategory.CREDENTIAL: RateLimitRule(
        category=RateLimitCategory.CREDENTIAL,
        limit=10,
        window_seconds=60,
        error_code="CREDENTIAL_RATE_LIMIT_EXCEEDED",
    ),
    RateLimitCategory.CONNECTOR: RateLimitRule(
        category=RateLimitCategory.CONNECTOR,
        limit=20,
        window_seconds=60,
        error_code="CONNECTOR_RATE_LIMIT_EXCEEDED",
    ),
    RateLimitCategory.POSTING: RateLimitRule(
        category=RateLimitCategory.POSTING,
        limit=30,
        window_seconds=60,
        error_code="CONNECTOR_RATE_LIMIT_EXCEEDED",
    ),
    RateLimitCategory.AI_HEAVY: RateLimitRule(
        category=RateLimitCategory.AI_HEAVY,
        limit=60,
        window_seconds=3600,
        error_code="AI_RATE_LIMIT_EXCEEDED",
    ),
    RateLimitCategory.DOCUMENT_UPLOAD: RateLimitRule(
        category=RateLimitCategory.DOCUMENT_UPLOAD,
        limit=60,
        window_seconds=3600,
        error_code="RATE_LIMIT_EXCEEDED",
    ),
    RateLimitCategory.ADMIN: RateLimitRule(
        category=RateLimitCategory.ADMIN,
        limit=30,
        window_seconds=60,
        error_code="RATE_LIMIT_EXCEEDED",
    ),
    RateLimitCategory.DEFAULT: RateLimitRule(
        category=RateLimitCategory.DEFAULT,
        limit=120,
        window_seconds=60,
        error_code="RATE_LIMIT_EXCEEDED",
    ),
}


# ---------------------------------------------------------------------------
# Path sets — always safe, never rate-limited
# ---------------------------------------------------------------------------

_SAFE_EXACT: frozenset[str] = frozenset({
    "/",
    "/health",
    "/health/",
    "/health/deep",
    "/health/ping",
    "/version",
    "/openapi.json",
    "/docs",
    "/docs/",
    "/redoc",
    "/redoc/",
    "/metrics",
})

_SAFE_PREFIXES: tuple[str, ...] = (
    "/health",
    "/static",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/version",
    "/metrics",
)

# Auth paths
_AUTH_EXACT: frozenset[str] = frozenset({
    "/auth/login",
    "/auth/register",
    "/auth/signup",
    "/auth/refresh",
})

_AUTH_PREFIXES: tuple[str, ...] = (
    "/auth/login",
    "/auth/register",
    "/auth/signup",
    "/auth/refresh",
    "/auth/password-reset",
    "/auth/totp",
)

# Credential write/test paths
_CREDENTIAL_EXACT: frozenset[str] = frozenset({
    "/balance-credentials/save",
    "/balance-credentials/test",
    "/rsge-credentials/save",
    "/rsge-credentials/test",
    "/email-collector/save",
})

_CREDENTIAL_PREFIXES: tuple[str, ...] = (
    "/balance-credentials/save",
    "/balance-credentials/test",
    "/rsge-credentials/save",
    "/rsge-credentials/test",
)

# Posting execute paths
_POSTING_PREFIXES: tuple[str, ...] = (
    "/posting/apply/",
    "/posting/balance/",
    "/posting/onec/",
    "/posting/oris/",
    "/posting/mock/",
)

# Connector / ERP paths
_CONNECTOR_PREFIXES: tuple[str, ...] = (
    "/erp/",
    "/erp-connectors/",
    "/balance-ge/",
    "/1c/",
)

# AI / OCR heavy paths
_AI_HEAVY_PREFIXES: tuple[str, ...] = (
    "/ai-journal/",
    "/ai-chat/",
    "/ai-recommend/",
    "/transaction-ai/",
    "/ai-classify/",
    "/chat/",
    "/claude-chat/",
    "/ocr/",
)

# Document upload paths
_DOCUMENT_PREFIXES: tuple[str, ...] = (
    "/documents/upload",
    "/bank-csv/",
    "/bank-statements/",
)

# Admin paths
_ADMIN_PREFIXES: tuple[str, ...] = (
    "/tenants/",
    "/billing/",
    "/admin/",
    "/settings/",
)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_rate_limit_category(path: str, method: str) -> str:
    """Classify a request path+method into a RateLimitCategory."""

    # Safe paths — never rate-limited
    if path in _SAFE_EXACT:
        return RateLimitCategory.SAFE
    for prefix in _SAFE_PREFIXES:
        if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix):
            return RateLimitCategory.SAFE

    # Auth
    if path in _AUTH_EXACT:
        return RateLimitCategory.AUTH
    for prefix in _AUTH_PREFIXES:
        if path.startswith(prefix):
            return RateLimitCategory.AUTH

    # Credential writes/tests — check exact first
    if path in _CREDENTIAL_EXACT:
        return RateLimitCategory.CREDENTIAL
    for prefix in _CREDENTIAL_PREFIXES:
        if path.startswith(prefix):
            return RateLimitCategory.CREDENTIAL

    # Posting execute (POST mutations on posting paths)
    for prefix in _POSTING_PREFIXES:
        if path.startswith(prefix):
            if method in ("POST", "PUT", "PATCH"):
                return RateLimitCategory.POSTING
            return RateLimitCategory.DEFAULT  # GET reads are default

    # Connector / ERP
    for prefix in _CONNECTOR_PREFIXES:
        if path.startswith(prefix):
            return RateLimitCategory.CONNECTOR

    # AI / OCR heavy
    for prefix in _AI_HEAVY_PREFIXES:
        if path.startswith(prefix):
            return RateLimitCategory.AI_HEAVY

    # Document upload
    for prefix in _DOCUMENT_PREFIXES:
        if path.startswith(prefix):
            return RateLimitCategory.DOCUMENT_UPLOAD

    # Admin
    for prefix in _ADMIN_PREFIXES:
        if path.startswith(prefix):
            return RateLimitCategory.ADMIN

    return RateLimitCategory.DEFAULT


def get_rate_limit_rule(category: str) -> RateLimitRule:
    """Return the rate-limit rule for a category. Falls back to DEFAULT."""
    return _RULES.get(category, _RULES[RateLimitCategory.DEFAULT])


def is_rate_limited_category(category: str) -> bool:
    """Return True if the category is actively rate-limited (not safe)."""
    return category in _RATE_LIMITED_CATEGORIES


# ---------------------------------------------------------------------------
# Key builder — no secrets allowed
# ---------------------------------------------------------------------------

def build_rate_limit_key(
    tenant_id: Optional[str],
    user_id: Optional[str],
    client_ip: Optional[str],
    category: str,
    path: Optional[str] = None,
) -> str:
    """Build a safe rate-limit key. Never includes tokens, passwords, or secrets.

    Format: rl:{category}:{tenant}:{identity}
    """
    tenant = tenant_id or "anon"

    if user_id:
        identity = f"u_{user_id}"
    elif client_ip:
        # Hash the IP — do not store raw IP in key for privacy
        identity = "ip_" + hashlib.sha256(client_ip.encode()).hexdigest()[:12]
    else:
        identity = "unknown"

    return f"rl:{category}:{tenant}:{identity}"


# ---------------------------------------------------------------------------
# Error builder — no secrets
# ---------------------------------------------------------------------------

def build_rate_limit_error(rule: RateLimitRule, retry_after_seconds: int) -> dict:
    """Build a safe 429 error envelope. No raw tenant data, no secrets."""
    return {
        "ok": False,
        "message": f"Rate limit exceeded. Please wait {retry_after_seconds} seconds.",
        "data": {"retry_after_seconds": retry_after_seconds},
        "error": {
            "code": rule.error_code,
            "details": (
                f"Rate limit: {rule.limit} requests per "
                f"{rule.window_seconds} seconds for category '{rule.category}'."
            ),
        },
    }
