"""Shared structured logging helpers for backend observability."""

from __future__ import annotations

import json
import logging
from typing import Any

_SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "file_bytes",
    "password",
    "payload",
    "refresh_token",
    "secret",
    "token",
    "raw_text",
    "document_contents",
}


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str) and len(value) > 512:
        return value[:512] + "..."
    return value


def structured_log(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Emit a compact JSON log line with sanitized fields."""
    payload: dict[str, Any] = {"event": event}
    for key, value in fields.items():
        if value is None or key in _SENSITIVE_KEYS:
            continue
        payload[key] = _normalize_value(value)
    logger.log(level, json.dumps(payload, ensure_ascii=False, default=str))
