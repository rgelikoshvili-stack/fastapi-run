# Bridge Hub P0 Fix Sprint Report

Date: 2026-08-14

## A) Summary

Implemented the P0 foundation fixes needed before Bridge Hub can safely continue toward the AI Accounting Assistant direction.

No production database migration was run. No production RS.ge endpoint was called. No live posting was executed.

## B) Files Changed

- `app/api/routes_claude_chat.py`
- `app/api/routes_rsge_credentials.py`
- `app/api/services/rsge_config.py`
- `app/api/services/posting_service.py`
- `app/api/services/ai_tool_registry.py`
- `app/storage/migrations/012_rsge_credentials_vault_metadata.sql`
- `tests/unit/test_p0_ai_assistant_foundation.py`
- `tests/unit/test_accounting_gap_12a.py`
- `tests/unit/test_approve_post_integration.py`
- `tests/unit/test_subscription_middleware.py`
- `tests/unit/test_subscription_sensitive_route_blocks.py`
- `docs/p0_fix_sprint_report.md`

## C) P0-1 Result: AI Approve Bypass

Fixed.

`_tool_approve_draft()` no longer updates `journal_drafts` directly. It now returns an approval-required response with the human approval endpoint. AI cannot directly approve drafts from chat.

## D) P0-2 Result: RS.ge Credential Plaintext Storage

Fixed for new saves.

`routes_rsge_credentials.py` now stores RS.ge passwords via `CredentialVaultService.save_credential()` and keeps only safe metadata in `tenant_rsge_credentials`.

Existing legacy plaintext rows are not migrated automatically in this sprint. A migration draft marks them as `rotation_required`.

## E) P0-3 Result: RS.ge Config Safety Module

Fixed.

Added `app/api/services/rsge_config.py` with safe defaults:

- RS.ge disabled by default
- read-only enabled by default
- dry-run enabled by default
- live actions disabled by default
- action-specific flags disabled by default
- production live action requires final approval flag

## F) P0-4 Result: FX Missing Rate Blocker

Fixed.

For `GEL`, exchange rate remains `1.0`. For non-GEL currencies, missing FX rate now raises `FX_RATE_MISSING` instead of silently posting with `1.0`.

## G) P0-5 Result: AI Visibility to RS.ge / Evidence / Triangle Data

Partially fixed as the foundation layer.

`ai_tool_registry.py` now includes read-only visibility for:

- `waybills`
- `tax_invoices`
- `commercial_invoices`
- `evidence_bundles`
- `triangle_matches`

Added tools:

- `get_rsge_document_status`
- `get_triangle_match_status`
- `get_accounting_risk_summary`

`routes_claude_chat.py` now injects summary counts for waybills, tax invoices, commercial invoices, triangle matches, evidence bundles, locked periods, and non-GEL drafts missing FX.

Remaining work: add richer natural-language QA tests and source-cited response formatting for accountant questions.

## H) Tests Run

Passed:

```text
python -m py_compile app/api/routes_claude_chat.py app/api/routes_rsge_credentials.py app/api/services/posting_service.py app/api/services/ai_tool_registry.py app/api/services/rsge_config.py tests/unit/test_p0_ai_assistant_foundation.py
```

Passed:

```text
standalone verification passed
```

Passed:

```text
python -m pytest tests/unit/test_p0_ai_assistant_foundation.py -v --tb=short
```

Result:

```text
7 passed, 1 warning in 0.12s
```

Broader targeted suite:

```text
python -m pytest \
  tests/unit/test_p0_ai_assistant_foundation.py \
  tests/unit/test_credential_vault_service.py \
  tests/unit/test_credential_vault_routes.py \
  tests/unit/test_credential_response_sanitizer.py \
  tests/unit/test_approval_service_quality.py \
  tests/unit/test_approval_payload_preview.py \
  tests/unit/test_dry_run_posting.py \
  tests/unit/test_posting_integrity.py \
  -v --tb=short
```

Result:

```text
168 passed, 1 warning in 50.08s
```

Former full-suite blockers were also stabilized:

- replaced a deprecated `asyncio.get_event_loop()` test call with `asyncio.run()`
- made trial subscription tests use the current test runtime date instead of an expired fixed date
- mocked ORIS connector readiness in the not-ready posting test instead of depending on demo-mode env defaults

Full unit suite:

```text
python -m pytest tests/unit/ -q --tb=short
```

Result:

```text
7202 passed, 3 skipped, 21 warnings in 412.34s
```

## I) Safety Scan Result

Safety scan was run over `app tests docs`.

Active P0 code patterns removed:

- no `SET status = 'approved', approved_by = 'chat_ai'` in active app code
- no `password TEXT NOT NULL` in `routes_rsge_credentials.py`
- no RS.ge credential INSERT writing `password`
- no `password = EXCLUDED.password`
- no non-GEL FX fallback continuing with `exchange_rate=1.0`

Expected remaining matches:

- historical docs still mention the original findings
- normal approval services still update `journal_drafts`
- tests assert token strings are not leaked
- `auth_service.py` has normal internal `ACCESS_TOKEN_EXPIRE_HOURS` constant

## J) Remaining Risks

- Existing RS.ge plaintext rows require approved migration/rotation.
- `rsge_submission_service.py` still references legacy credential storage and should be moved to vault retrieval before any live RS.ge use.
- AI visibility is now available at tool/query level, but end-to-end accountant chat behavior still needs integration tests.

## K) Next Recommended Sprint

1. Migrate `rsge_submission_service.py` to `CredentialVaultService.get_for_connector()`.
2. Add end-to-end AI chat tests for:
   - waybill without invoice
   - invoice without waybill
   - VAT mismatch
   - triangle mismatch
   - missing FX rate
3. Add a source-citation response format for AI answers.
4. Run local/test DB integration tests, not production DB.

Final line:

BRIDGE_HUB_P0_AI_ASSISTANT_FOUNDATION_FIXED
