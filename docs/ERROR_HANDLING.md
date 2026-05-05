# Bridge Hub — Error Handling Reference

## Standard error codes

All errors are returned as `{"ok": false, "error": {"code": "...", "details": "..."}}`.

### Approval errors

| Code | HTTP | Meaning |
|---|---|---|
| `NOT_FOUND` / `DRAFT_NOT_FOUND` | 404 | Draft does not exist or belongs to another tenant |
| `ALREADY_APPROVED` | 409 | Draft is already in `approved` state |
| `ALREADY_REJECTED` | 409 | Draft is already in `rejected` state |
| `DRAFT_LOCKED` | 409 | Concurrent request holds a row lock (retry after a moment) |
| `PERIOD_LOCKED` | 423 | Accounting period is locked — no changes allowed |
| `LOW_CONFIDENCE` | 422 | AI confidence below threshold for this amount bracket |
| `DUAL_APPROVAL_REQUIRED` | 202 | Amount exceeds CFO threshold; awaiting second approval |

### Posting errors

| Code | HTTP | Meaning |
|---|---|---|
| `NOT_APPROVED` | 409 | Draft must be in `approved` state before posting |
| `ALREADY_POSTED` | 409 | Draft was already successfully posted to this target |
| `PERIOD_LOCKED` | 423 | Period lock blocks posting |
| `IMBALANCED_LINES` | 422 | Journal lines do not balance (ΣDebit ≠ ΣCredit) |
| `CONNECTOR_ERROR` | 502 | ERP connector (Balance.ge / 1C) returned an error |
| `IDEMPOTENCY_CONFLICT` | 409 | Duplicate idempotency key — posting already attempted |

### Auth errors

| Code | HTTP | Meaning |
|---|---|---|
| `UNAUTHORIZED` | 401 | Missing or invalid JWT |
| `FORBIDDEN` | 403 | Valid JWT but role lacks required permission |
| `TOKEN_EXPIRED` | 401 | JWT has expired |

### General errors

| Code | HTTP | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Request body / query param failed Pydantic validation |
| `INTERNAL_ERROR` | 500 | Unhandled exception — check Cloud Run logs |
| `NOT_FOUND` | 404 | Generic resource not found |

## Error response helpers

```python
from app.api.response_utils import ok_response, error_response

# Success
return ok_response("Draft approved", {"id": 1, "status": "approved"})

# Error
return error_response("Draft not found", "NOT_FOUND", f"draft_id={draft_id}", status_code=404)
```

`error_response` signature:
```python
def error_response(
    message: str,
    code: str,
    details: str = "",
    status_code: int = 400,
) -> JSONResponse
```

## Exception hierarchy

```
asyncpg.LockNotAvailableError   → DRAFT_LOCKED (409)
asyncpg.UniqueViolationError    → IDEMPOTENCY_CONFLICT (409)
asyncpg.PostgresError           → INTERNAL_ERROR (500) — log + re-raise
Exception (bare)                → NEVER catch bare — always name the exception
```

## Logging conventions

```python
import logging
log = logging.getLogger(__name__)

# Expected / recoverable issues
log.warning("FX rate lookup failed for %s: %s — falling back to 1.0", currency, exc)

# Unexpected failures (will alert oncall)
log.error("Posting connector %s failed: %s", target, exc, exc_info=True)

# Structured fields added by middleware
# Every log line gets: severity, message, logger, time, correlation_id, tenant_id
```

## FX rate fallback WARNING

When `currency_rates` table is missing the rate for `(currency, date)`, posting
falls back to `exchange_rate = 1.0` **which is incorrect**. The log message is:

```
WARNING  FX rate lookup failed for USD→GEL (draft date=2026-01-15): ... —
falling back to exchange_rate=1.0 which IS INCORRECT.
Populate the currency_rates table to fix this.
```

Fix: ensure `_nbg_sync_loop` is running and the `currency_rates` table is populated.
The loop runs at startup and every 24 h from `main.py`.
