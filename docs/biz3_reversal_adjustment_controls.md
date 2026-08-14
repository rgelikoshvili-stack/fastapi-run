# BIZ-3: Reversal and Adjustment Controls

**Branch:** `codex/biz3-period-lock-reversal-controls`  
**Service:** `app/api/services/reversal_service.py`  
**Routes:** `app/api/routes_journal_entries.py`

---

## Accounting Safety Rules

1. **Original posted entries are NEVER modified or deleted.**
2. A reversal flips every line's debit/credit. The reversed entry must balance (DR = CR).
3. Both reversals and adjustments create new **drafts** in `pending_approval` status.
4. All drafts flow through the normal approval process before posting.
5. Duplicate reversal protection: a second reversal of the same entry raises `ValueError`.
6. Period locks apply to reversal/adjustment dates (not the original entry's date).

---

## Reversal Workflow

### Endpoint

```
POST /api/journal-entries/{draft_id}/reverse
Authorization: Bearer <JWT>   (approval:write required)

Body:
{
  "reversal_date":       "2026-01-05",
  "reason":              "Duplicate payment — customer credited 2025-12-31",
  "allow_closed_period": false
}
```

### Service: `create_reversal_draft()`

Located in `app/api/services/reversal_service.py`.

**Steps (in order):**

1. Validate `reason` is non-blank.
2. Parse `reversal_date` to `date` object.
3. Fetch original draft — raises `ValueError` if not found.
4. Assert original status is `posted` or `simulated_success`.
5. Check for duplicate reversal (`_reversal_already_exists`) — raises if found.
6. Check period lock on `reversal_date` (unless `allow_closed_period=True`).
7. `flip_lines(original.lines)` → new reversed lines.
8. Assert reversed lines are balanced.
9. Call `_validate_lines()` for account-level validation.
10. `INSERT INTO journal_drafts ... entry_type='reversal', status='pending_approval'`.
11. Emit `reversal_draft_created` audit event.

### `flip_lines(lines)` — pure function

```python
[{"account": "1120", "debit": 500, "credit": 0}, ...]
# becomes
[{"account": "1120", "debit": 0, "credit": 500}, ...]
```

- Returns a **new list** — original is never mutated.
- Preserves all other fields (account, description, etc.).
- If original was balanced, reversed is balanced.

### Response

```json
{
  "ok": true,
  "message": "Reversal draft #42 created for entry #17. Awaiting approval before posting.",
  "data": {
    "id": 42,
    "entry_type": "reversal",
    "reversal_of_draft_id": 17,
    "status": "pending_approval",
    "reversal_date": "2026-01-05",
    "lines": [...]
  }
}
```

---

## Adjustment Workflow

### Endpoint

```
POST /api/journal-entries/{draft_id}/adjust
Authorization: Bearer <JWT>   (approval:write required)

Body:
{
  "adjustment_date":     "2026-01-10",
  "reason":              "Reclassify from 7110 to 7210 — corrected cost center",
  "lines": [
    {"account": "7210", "debit": 1000, "credit": 0},
    {"account": "7110", "debit": 0,    "credit": 1000}
  ],
  "allow_closed_period": false
}
```

### Service: `create_adjustment_draft()`

**Steps (in order):**

1. Validate `reason` non-blank, `lines` non-empty.
2. Parse `adjustment_date` to `date` object.
3. Normalize lines via `_normalize_lines()`.
4. Assert lines are balanced (DR = CR) — raises `ValueError` if not.
5. Call `_validate_lines()` for account-level validation.
6. Fetch original draft — raises `ValueError` if not found.
7. Check period lock on `adjustment_date` (unless `allow_closed_period=True`).
8. `INSERT INTO journal_drafts ... entry_type='adjustment', status='pending_approval'`.
9. Emit `adjustment_draft_created` audit event.

**Note:** Adjustment does not require original to be `posted` — you can create a
correcting entry referencing any draft. Balance check happens **before** `_validate_lines`
to produce a clear English error instead of the Georgian validation message.

---

## DB Schema Changes (Migration)

Added to `journal_drafts` table at startup via `app/startup/migrations.py`:

```sql
ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS reversal_of_draft_id INTEGER;
ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS reversal_reason       TEXT;
ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS entry_type            TEXT DEFAULT 'normal';
```

All three are idempotent (`IF NOT EXISTS`). `entry_type` values: `normal`, `reversal`, `adjustment`.

---

## Duplicate Reversal Protection

```python
async def _reversal_already_exists(conn, original_draft_id, tenant_id) -> bool:
    """Return True if a non-rejected reversal draft for original_draft_id exists."""
    SELECT id FROM journal_drafts
    WHERE tenant_id = $1
      AND reversal_of_draft_id = $2
      AND status NOT IN ('rejected')
    LIMIT 1
```

If a reversal exists (not rejected), `create_reversal_draft` raises:
```
ValueError: "A non-rejected reversal for draft {id} already exists.
Post a second correcting adjustment entry instead."
```

---

## Admin Override: `allow_closed_period=True`

Both endpoints accept `allow_closed_period` in the request body. When `true`,
`assert_period_open()` is skipped, allowing a reversal or adjustment dated in a
locked period. This requires the actor to have `approval:write` permission (same as
the normal path) — no additional permission gate is defined, as this is intended for
CFO/Admin-level correcting entries.

---

## Audit Events

| Event | Payload Fields |
|-------|---------------|
| `reversal_draft_created` | `entity_id`, `original_draft_id`, `reversal_date`, `reason`, `actor`, `lines_count` |
| `adjustment_draft_created` | `entity_id`, `original_draft_id`, `adjustment_date`, `reason`, `actor`, `lines_count` |

---

## Error Codes

| Code | HTTP | When |
|------|------|------|
| `VALIDATION_ERROR` | 400 | Missing required fields, unbalanced lines, original not found |
| `PERIOD_LOCKED` | 400 | Reversal/adjustment date is in a locked period |
| `REVERSAL_ERROR` | 500 | Unexpected DB or service error during reversal |
| `ADJUSTMENT_ERROR` | 500 | Unexpected DB or service error during adjustment |

---

## Testing

Unit tests: `tests/unit/test_reversal_adjustment_biz3.py`

- `TestFlipLines` — 8 tests (DR→CR, CR→DR, untouched original, multi-line, nets to zero)
- `TestLinesBalanced` — 5 tests
- `TestCreateReversalDraft` — 4 tests (reason required, blank reason, lines inverted, DR=CR)
- `TestReversalIntoClosedPeriod` — 2 tests (blocked when locked, admin override bypasses check)
- `TestDuplicateReversal` — 1 test
- `TestAdjustmentDraftValidation` — 5 tests (reason, lines, unbalanced, balanced, closed period)
- `TestPostingPreservation` — 2 tests (original never mutated)

RBAC/audit tests: `tests/unit/test_period_lock_rbac_audit_biz3.py`

- `TestRBACLockUnlock` — 8 tests
- `TestAuditLockUnlock` — 7 tests
- `TestAuditNoSecrets` — 4 tests (no credentials in audit payload)
- `TestDeniedActionLogging` — 2 tests
- `TestBIZ3ServiceImports` — 4 import smoke tests
