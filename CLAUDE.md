# Bridge Hub — Engineering Reference

## Quick start

```bash
# Install deps
pip install -r requirements.txt

# Run dev server (no real DB required for unit tests)
JWT_SECRET=dev-secret uvicorn main:app --reload

# Run unit tests (no DB, no external services)
JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL="" \
  python -m pytest tests/unit/ --ignore=tests/unit/test_document_upload.py -q

# Run all tests (requires a real Postgres DATABASE_URL)
DATABASE_URL="postgresql://..." python -m pytest tests/ -q
```

## Required environment variables

| Variable | Description | Required |
|---|---|---|
| `DATABASE_URL` | psycopg2-format Postgres URL (`postgresql://user:pw@host/db`) | yes |
| `JWT_SECRET` | HMAC-SHA256 signing secret (≥ 32 chars in prod) | yes |
| `ANTHROPIC_API_KEY` | Claude API key for AI classification | yes |
| `GCS_BUCKET_NAME` | GCS bucket for document storage | no (falls back to DB) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP service account JSON | no |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins | no (has default list) |
| `TEST_MODE` | Set to `1` to skip real-DB calls in unit tests | tests only |

## Deploy to Cloud Run

```bash
gcloud run deploy fastapi-run \
  --source . \
  --region europe-west1 \
  --set-env-vars DATABASE_URL=...,JWT_SECRET=...,ANTHROPIC_API_KEY=... \
  --allow-unauthenticated
```

See `credentials.md` in memory for the exact production command.

## Project layout

```
main.py                         FastAPI app, middleware, lifespan hooks
app/
  api/
    routes_*.py                 All HTTP route handlers (one file per domain)
    services/                   Business logic (called by routes, never by each other's routes)
      approval_service.py       Approve / reject / correct journal drafts
      approval_patterns.py      Pattern-reinforcement helpers (extracted from approval_service)
      posting_service.py        ERP connector dispatch (Balance.ge, 1C)
      posting_helpers.py        Pure decimal/line-validation utilities (no DB)
      tenant_config_service.py  Per-tenant settings (tenant_settings table)
      payroll_service.py        Payroll draft generation
      ...
    middleware/
      auth_middleware.py        JWT verification → request.state.{user_id, role, tenant_id}
      rbac_middleware.py        Permission enforcement via compiled permission map
      tenant_middleware.py      Sets request.state.tenant_id from header / JWT
      audit_log_middleware.py   Writes every mutating request to audit_log table
      correlation_middleware.py Attaches X-Correlation-ID to every request
    policy/
      permission_map.py         PERMISSION_MAP + COMPILED_PERMISSION_MAP (O(1) lookup)
    response_utils.py           ok_response() / error_response() helpers
  core/
    router_registry.py          register_routers(app) — single place to include all routers
  knowledge/
    __init__.py                 Re-exports all public symbols
    chart_of_accounts.py        CHART_OF_ACCOUNTS, TAX_RATES, ACCA_STANDARDS
    tax_rules.py                Tax calculators (VAT, payroll, CIT, withholding, depreciation)
    knowledge_loader.py         KB load, learn_new_rule, migrate_json_to_db
    journal_builder.py          classify_transaction, build_journal_from_text
  startup/
    migrations.py               Runs all DDL migrations at startup (psycopg2 sync)
    background.py               autopilot_loop, decay_loop, email_poller_loop
bridge_hub_knowledge.py         DEPRECATED shim — imports from app/knowledge/, do not add code
```

## Response envelope

Every API response must use the standard envelope:

```json
{ "ok": true,  "message": "Human-readable summary", "data": {...}, "error": null }
{ "ok": false, "message": "Human-readable summary", "data": null,  "error": {"code": "SNAKE_CODE", "details": "..."} }
```

Use the helpers in `app/api/response_utils.py`:
```python
from app.api.response_utils import ok_response, error_response

return ok_response("Draft approved", {"id": draft_id, "status": "approved"})
return error_response("Draft not found", "NOT_FOUND", f"id={draft_id}")
```

Never return bare `{"ok": True, ...}` dicts — the test suite checks for this.

## Database access patterns

Two DB layers coexist. Do not mix them within the same function.

| Layer | When to use | How to get a connection |
|---|---|---|
| asyncpg (async) | All new route handlers and services | `async with get_conn() as conn:` |
| psycopg2 (sync) | Migration scripts, legacy services | `conn = get_db()` / `get_db_sync()` |

All asyncpg queries use `$1, $2, ...` placeholders. Use `_q(sql)` to convert
`%s` placeholders to numbered ones (legacy SQL ported from psycopg2).

### Tenant isolation

Every query against tenant-scoped tables **must** include `WHERE tenant_id = $N`.
Retrieve the tenant with:
```python
tenant_id = getattr(request.state, "tenant_id", "default")
```
Never fall back silently to `"default"` in production queries — use `require_permission`
which also asserts that `tenant_id` is set.

## RBAC

Permissions are defined in `app/api/policy/permission_map.py` (PERMISSION_MAP list)
and `app/api/authz.py` (ROLE_PERMISSIONS dict).

To protect an endpoint:
```python
from app.api.rbac import require_permission

@router.post("/approve/{draft_id}")
async def approve(draft_id: int, request: Request):
    require_permission(request, "approval:write")
    ...
```

The compiled map (`COMPILED_PERMISSION_MAP`) is a method-indexed dict for fast O(fewer-scans) lookup.
Do not add a linear scan — the test `test_rbac_uses_compiled_matcher_not_local_linear_scan` will fail.

## Approval flow

```
journal_drafts.status transitions:
  drafted → approved   (single-approver path, amount < CFO threshold)
  drafted → awaiting_cfo → approved  (dual-approval path, amount ≥ CFO threshold)
  drafted / approved → rejected
  approved → posted    (after ERP connector succeeds)
```

CFO threshold is configurable per tenant via `tenant_settings`:
```python
from app.api.services.tenant_config_service import get_tenant_setting
threshold = await get_tenant_setting(tenant_id, "approval.cfo_threshold_gel", 10000.0)
```

Race condition protection: `approve_draft_service` uses `SELECT … FOR UPDATE NOWAIT`.
`asyncpg.LockNotAvailableError` → `DRAFT_LOCKED` response (HTTP 409).

## Period locks

Periods are locked via the `period_locks` table. The approval and posting services
check `is_period_locked(conn, tenant_id, date)` before any state transition.
A locked period returns `PERIOD_LOCKED` (HTTP 423 or 409 depending on caller).

## Adding a new endpoint

1. Create or reuse `app/api/routes_<domain>.py`
2. Add the router to `app/core/router_registry.py` inside `register_routers()`
3. Add a permission entry to `app/api/policy/permission_map.py` (PERMISSION_MAP)
4. Add the permission to the relevant roles in `app/api/authz.py` (ROLE_PERMISSIONS)
5. Return responses with `ok_response()` / `error_response()`
6. Write at least one unit test in `tests/unit/`

## Testing strategy

| Suite | Location | What it tests |
|---|---|---|
| Unit (no DB) | `tests/unit/` | Services, helpers, response shapes; all DB mocked |
| Integration | `tests/integration/` | Full pipeline with a real Postgres instance |

Unit tests patch at the module where a name is **used**, not where it is **defined**:
```python
# correct — patches where approval_service imports it
patch("app.api.services.approval_service.get_conn", ...)
# correct — patches where approval_patterns imports it
patch("app.api.services.approval_patterns.mark_pattern_success", ...)
```

For lazy imports inside function bodies, patch at the defining module:
```python
patch("app.api.services.tenant_config_service.get_tenant_setting", ...)
```

## Immutable core — do not modify without discussion

These modules encode the core ML/pattern logic. Changing them without understanding
the full feedback loop risks silently degrading classification accuracy:

- `app/api/engines/pattern_engine.py`
- `app/api/services/learning_service.py`
- `app/api/services/pattern_decay_service.py`
- `app/api/transaction_classifier.py`

## Safety rules

- **Never** bypass RBAC (`require_permission`) for an endpoint that mutates data.
- **Never** omit `tenant_id` filter on any query against a tenant-scoped table.
- **Never** commit `JWT_SECRET`, `DATABASE_URL`, or any API key to the repo.
- **Never** use `import *` — the linter and `test_knowledge_compat.py` will catch it.
- **Never** add a bare `except:` — always catch a specific exception and log with `log.warning()`.
- FX rate fallback (exchange_rate=1.0) logs a WARNING. Fix by populating `currency_rates`.
