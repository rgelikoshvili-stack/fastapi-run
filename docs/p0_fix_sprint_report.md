# P0 Fix Sprint Report — AI Accounting Assistant Foundation
**Date:** 2026-08-14  
**Sprint:** P0 AI Assistant Foundation Hardening  
**Status:** COMPLETE — 63/63 tests passed, safety scan clean

---

## A. Summary

Five confirmed P0 security and correctness gaps in the AI accounting assistant were identified, fixed, tested, and verified clean. All fixes were additive or replacement-level; no existing behaviour was changed outside the targeted defects.

| P0 | Description | Severity | Status |
|----|-------------|----------|--------|
| P0-1 | AI could approve drafts directly — bypassed approval_service, period locks, CFO gate, audit log, RBAC | CRITICAL | ✅ Fixed |
| P0-2 | RS.ge portal password stored in plaintext TEXT column instead of CredentialVaultService | CRITICAL | ✅ Fixed |
| P0-3 | `rsge_config.py` module never existed; 2 integration tests failed with ModuleNotFoundError | HIGH | ✅ Fixed |
| P0-4 | Non-GEL posting silently used exchange_rate=1.0 when FX rate was missing — financially wrong | CRITICAL | ✅ Fixed |
| P0-5 | AI could only see journal_drafts + invoices; blind to waybills, tax_invoices, triangle_matches, evidence_bundles | HIGH | ✅ Fixed |

---

## B. Files Changed

### New files
| File | Purpose |
|------|---------|
| `app/api/services/rsge_config.py` | P0-3: RS.ge feature flag module with safe defaults |
| `app/storage/migrations/012_rsge_credentials_vault_migration.sql` | P0-2: DDL draft (not executed) |
| `tests/unit/test_p0_rsge_config.py` | 17 tests for P0-3 |
| `tests/unit/test_p0_ai_approve_bypass.py` | 14 tests for P0-1 |
| `tests/unit/test_p0_fx_rate_blocker.py` | 8 tests for P0-4 |
| `tests/unit/test_p0_rsge_credentials_vault.py` | 7 tests for P0-2 |
| `tests/unit/test_p0_ai_visibility.py` | 17 tests for P0-5 |

### Modified files
| File | Change |
|------|--------|
| `app/api/routes_claude_chat.py` | P0-1: replaced direct-approve DB call with approval_required return; P0-5: extended system prompt context |
| `app/api/routes_rsge_credentials.py` | P0-2: vault-first credential saves; rotation_required for legacy rows |
| `app/api/services/posting_service.py` | P0-4: FxRateMissingError class + raise instead of silent 1.0 fallback |
| `app/api/services/ai_tool_registry.py` | P0-5: 7 source tables in search; 3 new tools |

---

## C. P0-1: AI Approve Bypass — FIXED

**Root cause:** `_tool_approve_draft` in `routes_claude_chat.py` executed `UPDATE journal_drafts SET status='approved', approved_by='chat_ai'` directly, bypassing:
- `approval_service.approve_draft_service` (with period lock check, CFO gate, row lock, audit event)
- RBAC enforcement
- Idempotency guard
- CFO dual-approval gate (≥₾10,000)

**Fix:** `_tool_approve_draft` now returns `{"approval_required": True, "action": "approve_draft", "next_endpoint": "/api/approval/approve/{id}", ...}`. No DB access whatsoever. The human accountant must call the approval endpoint.

**SYSTEM_PROMPT** updated to state in Georgian: "AI ვერ ასრულებს პირდაპირ დამტკიცებას".

**Tests:** 14 tests — all pass. Key: `test_approve_draft_no_db_access` removes DATABASE_URL from env and verifies the call still succeeds (proving no DB touch).

---

## D. P0-2: Plaintext RS.ge Credentials — FIXED

**Root cause:** `routes_rsge_credentials.py` wrote `body.password` directly into `tenant_rsge_credentials.password TEXT NOT NULL`. The `CredentialVaultService` AES-256-GCM vault was never called.

**Fix:**
1. `save_creds` now calls `CredentialVaultService().save_credential(conn, ...)` to encrypt and store the password.
2. `tenant_rsge_credentials.password` receives the marker `'[stored-in-vault]'` and is now nullable (DDL in `_ENSURE_SCHEMA`).
3. `credential_vault_ref` column stores the UUID reference to `credential_vault_credentials(id)`.
4. `credential_status` tracks `active` / `rotation_required` / `legacy_plaintext`.
5. Existing rows with plaintext passwords are flagged `rotation_required` by the `_ENSURE_SCHEMA` UPDATE.
6. On vault failure: returns `CREDENTIAL_VAULT_ERROR` — **no fallback to plaintext**.
7. `get_status` and `test_connection` never return the password field.

**Migration 012** (draft at `app/storage/migrations/012_rsge_credentials_vault_migration.sql`): makes password nullable, adds columns, flags legacy rows. NOT to be executed without explicit production approval.

**Tests:** 7 tests — all pass.

---

## E. P0-3: Missing rsge_config Module — FIXED

**Root cause:** `rsge_config.py` was referenced in integration tests and planned but never created. Two integration tests failed with `ModuleNotFoundError: No module named 'app.api.services.rsge_config'`.

**Fix:** Created `app/api/services/rsge_config.py` with:
- `is_enabled()` → default `False`
- `live_actions_enabled()` → default `False`
- `read_only()` → default `True`
- `dry_run()` → default `True`
- `test_mode()` → default `False`
- `allow_action(action_type)` → 5-gate hierarchy (enabled + not read_only + not dry_run + live_actions + action-specific flag)

Six action types covered: `confirm`, `reject`, `cancel`, `correct`, `activate`, `waybill_action`.

**Tests:** 17 tests — all pass. Key: parametrized test confirms all 6 actions default to False.

---

## F. P0-4: Silent FX Rate Fallback — FIXED

**Root cause:** In `posting_service.py::_draft_to_posting_payload`, the `except` block after `await currency_service.get_rate_async(...)` silently set `exchange_rate = 1.0` for any non-GEL currency when the rate table was empty. This produced wrong GEL amounts for EUR/USD postings.

**Fix:**
```python
class FxRateMissingError(ValueError):
    """Raised when FX rate is not available for a non-GEL posting."""
```
The `except` block now raises `FxRateMissingError` with a descriptive message including currency and date.

In both `apply_posting_service` and `dry_run_posting_service`:
```python
except FxRateMissingError as _fx_missing:
    await tr.rollback()
    return error_response(str(_fx_missing), code="FX_RATE_MISSING", ...)
```

**Tests:** 8 tests — all pass. Key tests: GEL still uses 1.0 correctly; non-GEL missing rate raises the error; connector is never called when FX is missing.

---

## G. P0-5: AI Visibility Gaps — FIXED

**Root cause:** `ai_tool_registry.py::_search_documents` only queried `journal_drafts`, `invoices`, `outgoing_invoices`. The AI assistant had no visibility into:
- `waybills` — RS.ge waybill imports
- `tax_invoices` — VAT invoice imports
- `commercial_invoices` — commercial invoice imports
- `triangle_matches` — 3-way match results
- `evidence_bundles` — document-to-draft linkages

**Fix — search expansion:** `_search_documents` now queries 7 source tables. Each additional table uses the tenant_id filter and returns `source_table` tag for provenance.

**Fix — system prompt context:** `_fetch_db_context` now injects into every AI chat:
- Waybill / tax_invoice / triangle mismatch / evidence bundle counts
- Period lock status for the current month
- FX rate availability warning

**Fix — 3 new tools:**
1. `get_rsge_document_status(document_number)` — look up waybill or tax_invoice by number
2. `get_triangle_match_status()` — returns match risk level (HIGH/MEDIUM/LOW) per match_score
3. `get_accounting_risk_summary()` — checks 6 risk types: waybill_without_invoice, triangle_mismatch, FX_rate_missing, period_locked, high_amount_missing_accounts, low_confidence_drafts

All new tools are read-only, tenant-scoped, and never return secrets.

**Tests:** 17 tests — all pass. Key: `test_ai_tools_cannot_call_rsge_mutations` verifies by source inspection that no tool calls RS.ge mutation endpoints.

---

## H. Tests Run

```
JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL="" \
  python -m pytest tests/unit/test_p0_*.py -v --tb=short
```

**Result: 63 passed, 0 failed, 5 warnings in 0.64s**

| Test file | Tests | Result |
|-----------|-------|--------|
| test_p0_rsge_config.py | 17 | ✅ all pass |
| test_p0_ai_approve_bypass.py | 14 | ✅ all pass |
| test_p0_fx_rate_blocker.py | 8 | ✅ all pass |
| test_p0_rsge_credentials_vault.py | 7 | ✅ all pass |
| test_p0_ai_visibility.py | 17 | ✅ all pass |

---

## I. Safety Scan Result

Checked app/, tests/, docs/ for:

| Pattern | Result |
|---------|--------|
| `approved_by = 'chat_ai'` in app code | ✅ NOT FOUND |
| `UPDATE journal_drafts SET status='approved'` outside approval_service | ✅ Only in approval_service.py and routes_approval.py (correct paths) |
| `exchange_rate = 1.0` (silent fallback) | ✅ NOT FOUND |
| `password TEXT NOT NULL` in rsge_credentials table | ✅ NOT FOUND (only email_collector.py, unrelated) |
| `RSGE_LIVE_ACTIONS_ENABLED=true` hardcoded | ✅ Only in rsge_config.py docstrings |
| `BALANCE_API_KEY=` hardcoded | ✅ Only in .env.example |
| `POSTED_LEDGER_WRITES_ENABLED=false` in app code | ✅ Only in H69/H70 test/doc files |
| `chat_ai` in app code | ✅ NOT FOUND |

**Scan result: CLEAN**

---

## J. Remaining Risks

| Risk | Severity | Notes |
|------|----------|-------|
| Migration 012 not yet run in prod | MEDIUM | `012_rsge_credentials_vault_migration.sql` is a draft. Requires production approval, maintenance window, and backup verification before running. |
| Existing plaintext RS.ge passwords in prod DB | MEDIUM | Marked `rotation_required` after migration 012 runs. Until then, existing credentials still use plaintext column. No new saves will be plaintext. |
| FX rate table may be empty for some tenants | MEDIUM | Non-GEL postings will fail with `FX_RATE_MISSING` until `currency_rates` is populated. Operators must populate before posting non-GEL entries. This is the correct behavior (fail safe). |
| RS.ge live integration still read-only | LOW | All RS.ge action flags default to False. Live integration remains disabled until explicitly enabled per-tenant. |
| AI trust boundary (rate limiting) | LOW | AI chat endpoint currently has no per-tenant rate limit. Add in next sprint. |

---

## K. Next Sprint

1. **Run migration 012** (with production approval, maintenance window, PITR backup point)
2. **Populate `currency_rates`** table for all tenants with active non-GEL invoices
3. **AI rate limiting** — add per-tenant request cap on `/api/claude-chat`
4. **RS.ge live pilot** — after migration 012 is confirmed and at least one tenant re-saves credentials, enable `RSGE_ENABLED=true` + `RSGE_READ_ONLY=true` for read-only waybill sync
5. **Credential rotation UX** — UI flow for `rotation_required` tenants to re-save via the vault path
