"""app/api/services/credential_response_sanitizer.py

Strips forbidden credential field names from status/settings API responses
before they are returned to HTTP clients.

Applied at the service or route boundary as a final safety layer.
Never logs raw secret values.
"""
from __future__ import annotations

from typing import Any, Optional

FORBIDDEN_CREDENTIAL_RESPONSE_KEYS: frozenset[str] = frozenset({
    "api_key",
    "apikey",
    "apiKey",
    "password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "client_secret",
    "encrypted_value",
    "raw_secret",
    "decrypted_value",
    "private_key",
})

# Normalized (lowercased) lookup set for case-insensitive key matching
_FORBIDDEN_LOWER: frozenset[str] = frozenset(k.lower() for k in FORBIDDEN_CREDENTIAL_RESPONSE_KEYS)


def sanitize_credential_response(data: Any) -> Any:
    """Recursively strip forbidden credential keys from dicts and lists.

    Safe to call on any response structure — non-dict/list values pass through.
    """
    if isinstance(data, dict):
        return {
            k: sanitize_credential_response(v)
            for k, v in data.items()
            if k.lower() not in _FORBIDDEN_LOWER
        }
    if isinstance(data, list):
        return [sanitize_credential_response(item) for item in data]
    return data


def assert_no_raw_secret_fields(data: Any) -> None:
    """Raise ValueError if any forbidden key is present at any depth.

    The error message never includes the secret value itself.
    """
    if isinstance(data, dict):
        for k, v in data.items():
            if k.lower() in _FORBIDDEN_LOWER:
                raise ValueError(f"Forbidden credential field in response: key={k!r}")
            assert_no_raw_secret_fields(v)
    elif isinstance(data, list):
        for item in data:
            assert_no_raw_secret_fields(item)


def mask_known_secret_value(value: str) -> str:
    """Return a masked hint — last 4 chars if long enough, else stars only."""
    if len(value) >= 8:
        return "****" + value[-4:]
    return "****"


def safe_configured_status(
    provider: str,
    configured: bool,
    *,
    mode: Optional[str] = None,
    masked_hint: Optional[str] = None,
    last_test_status: Optional[str] = None,
    last_tested_at: Optional[Any] = None,
    credential_status: Optional[str] = None,
) -> dict:
    """Build a safe credential status dict containing no raw secret fields."""
    result: dict = {
        "provider": provider,
        "configured": configured,
        "mode": mode if mode is not None else ("live" if configured else "demo"),
    }
    if masked_hint is not None:
        result["masked_hint"] = masked_hint
    if last_test_status is not None:
        result["last_test_status"] = last_test_status
    if last_tested_at is not None:
        result["last_tested_at"] = last_tested_at
    if credential_status is not None:
        result["credential_status"] = credential_status
    return result
