# Bridge Hub — Architecture Overview

## System context

Bridge Hub is a Georgian-market accounting automation backend deployed on Google Cloud Run.
It bridges document ingestion (PDF/email invoices) through AI classification into ERP systems
(Balance.ge, 1C). All amounts are in GEL by default; foreign-currency docs are converted
via daily NBG (National Bank of Georgia) exchange rates.

```
┌────────────┐     ┌───────────────┐     ┌─────────────────────┐
│  Client    │────▶│  FastAPI app  │────▶│  PostgreSQL (Neon)  │
│  (browser/ │     │  Cloud Run    │     └─────────────────────┘
│   mobile)  │     │  europe-west1 │────▶│  Google Cloud       │
└────────────┘     │               │     │  Storage (docs)     │
                   │               │────▶│  Anthropic API      │
                   │               │     │  (Claude 3)         │
                   └───────────────┘────▶│  NBG API (FX rates) │
                                         └─────────────────────┘
```

## Request lifecycle

```
Request
  │
  ├─ correlation_middleware     — attach X-Correlation-ID
  ├─ tenant_middleware          — set request.state.tenant_id
  ├─ auth_middleware            — verify JWT → request.state.{user_id, role, authenticated}
  ├─ rbac_middleware            — match_permission(method, path) → check ROLE_PERMISSIONS
  ├─ audit_log_middleware       — write mutating requests to audit_log table
  │
  └─ Route handler
       │
       ├─ require_permission()  — explicit in-handler permission check (belt+suspenders)
       ├─ Service call          — all business logic lives in app/api/services/
       └─ ok_response() / error_response()  — standard envelope
```

Middleware registration order in `main.py` (Starlette executes in reverse):
innermost → auth → rbac → audit → correlation → outermost

## Core data model

```
journal_drafts          — AI-classified transactions awaiting human approval
  id, tenant_id, status, amount, date, description, partner, currency
  account_code, debit_account, credit_account
  confidence, classification_source, pattern_matched_on
  lines_json            — [{account_code, debit, credit}] balanced journal lines

posting_log             — immutable record of every ERP push attempt
  draft_id, tenant_id, target (balance|onec|...), status, idempotency_key
  posted_at, error_message

learning_patterns       — feedback-loop rules learned from user approvals
  tenant_id, pattern_type, pattern_value, account_code, hit_count, decay_score

tenant_settings         — per-tenant configuration key-value store
  tenant_id, key, value_json

period_locks            — accounting period locks (blocks approve/post)
  tenant_id, period_start, period_end, locked_by, locked_at

audit_log               — immutable request audit trail
  tenant_id, user_id, method, path, status_code, duration_ms, correlation_id
```

## AI classification pipeline

```
Document / description text
  │
  ├─ 1. Pattern engine (learning_patterns table)
  │       exact match → high confidence
  │       fuzzy match → medium confidence
  │
  ├─ 2. Knowledge base rules (_CLS_RULES in app/knowledge/journal_builder.py)
  │       Georgian tax/accounting rules, chart of accounts
  │
  ├─ 3. Claude API (fallback for low-confidence or unknown)
  │       app/api/services/llm_service.py + ai_service.py
  │
  └─ journal_drafts row  (status=drafted, confidence=0.0-1.0)
```

Confidence thresholds (defined as named constants in `approval_service.py`):
- `CONFIDENCE_THRESHOLD_HIGH_RISK = 0.95` (amounts ≥ 1000 GEL)
- `CONFIDENCE_THRESHOLD_DEFAULT   = 0.85`
- `CONFIDENCE_THRESHOLD_LOW_RISK  = 0.75` (amounts < 50 GEL)

## Approval flow state machine

```
                  ┌──────────┐
                  │ drafted  │◀── AI creates
                  └────┬─────┘
                       │ approve() [amount < CFO threshold]
                       ▼
              ┌─────────────────┐
              │    approved     │
              └────────┬────────┘
                       │ post()
                       ▼
               ┌──────────────┐
               │    posted    │
               └──────────────┘

         OR dual-approval path:
                  ┌──────────┐
                  │ drafted  │
                  └────┬─────┘
                       │ approve() [amount ≥ CFO threshold]
                       ▼
             ┌──────────────────┐
             │  awaiting_cfo    │
             └────────┬─────────┘
                      │ cfo_approve()
                      ▼
              ┌─────────────────┐
              │    approved     │
              └────────┬────────┘
                       │ post()
                       ▼
               ┌──────────────┐
               │    posted    │
               └──────────────┘

  Any state → rejected  (by reject())
```

## Background tasks (startup/background.py)

| Task | Interval | Purpose |
|---|---|---|
| `autopilot_loop` | 60 s | Auto-approve high-confidence drafts below threshold |
| `decay_loop` | 1 h | Decay hit-count on stale learning patterns |
| `email_poller_loop` | 5 min | Poll connected mailboxes for new invoice emails |
| `_nbg_sync_loop` | 24 h | Sync NBG currency rates to `currency_rates` table |

## ERP connectors

Connectors live in `app/integrations/` and are dispatched from `posting_service.py`.
Each connector receives the journal entry payload and returns `{ok, ref_id, error}`.

Idempotency: each posting attempt has an SHA-256 `idempotency_key` over
`{draft_id, tenant_id, target}`. A duplicate key in `posting_log` → 409 Conflict.

## Knowledge base modules

```
app/knowledge/
  chart_of_accounts.py   Georgian Chart of Accounts (6xxx/7xxx/…), ACCA standards, VAT rates
  tax_rules.py           Tax calculators: VAT (18%), payroll (PIT 20% + PAYG 2%),
                         CIT (15% on distributed profit), withholding (5-10%)
  knowledge_loader.py    Load static JSON files + DB learned rules, migrate_json_to_db
  journal_builder.py     classify_transaction(), build_journal_from_text(), _CLS_RULES
```

`bridge_hub_knowledge.py` (root) is a DEPRECATED backward-compatibility shim.
It re-exports everything from `app/knowledge/`. Do not add code there.

## Security model

- JWT authentication (HS256). Access tokens: 15 min TTL. Refresh tokens: 7 days.
- RBAC: 6 roles (admin, accountant, cfo, viewer, auditor, employee). Permissions defined in
  `app/api/authz.py` + `app/api/policy/permission_map.py`.
- Tenant isolation: every DB query filters by `tenant_id` from JWT claim.
- Rate limiting: SlowAPI (Redis or in-memory). Login: 5/min. Approval: 30/min.
- Security headers: CSP, HSTS, X-Frame-Options, X-Content-Type-Options (see `app/api/security.py`).
- HTTPS enforced via `X-Forwarded-Proto` redirect middleware.

## Key design decisions

**Dual DB layer (asyncpg + psycopg2)**: asyncpg is used for all route handlers because it is
non-blocking. psycopg2 is kept for migration scripts and a few legacy services that predate the
async migration. They should not be mixed within the same request path.

**Pattern learning feedback loop**: Every approval/rejection triggers `mark_pattern_success` /
`mark_pattern_failure` in the pattern engine. This incrementally improves classification
accuracy without retraining a model. The `decay_loop` prevents stale patterns from dominating.

**Pessimistic locking on approve**: `SELECT … FOR UPDATE NOWAIT` prevents double-approval
in concurrent requests. `LockNotAvailableError` → `DRAFT_LOCKED` (409). This is safer than
optimistic locking for an accounting system where a double-approved transaction could cause
a real financial discrepancy.
