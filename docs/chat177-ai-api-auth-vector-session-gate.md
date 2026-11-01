# Bridge Hub — Chat177 /api/ai RBAC, Tenant/User sessions and vector safety

**2026-10-29 | Draft PR #154 only | Production HOLD.**
**Independently CI-verified code SHA:** `4428a5311f50e5216202cbf6b75d8f4fb504c9a0`.

No main merge, Production Cloud Run deploy, actual Cloud SQL/Redis/GCS or
provider changes, migration DDL, Windows original/index/worktree/ACL
mutation, live customer data or credentials.

## 1. Confirmed Chat177 findings and safe Draft fixes

- **Public AI bypass:** `rbac_middleware` previously allowed the whole
  `/api/ai/` prefix to skip RBAC. The exception is removed. A method-aware
  permission map explicitly requires `chat:use` for default AI endpoints,
  `approval:write` for `/api/ai/action/confirm`, and `patterns:manage`
  for `/api/ai/learn`, `/api/ai/index` and vector stats. Route-level
  auth and signed Tenant/transaction context are also checked.
- **Calculator route request confusion:** VAT, CIT, payroll, dividends,
  depreciation, classify and learn previously passed a Pydantic **body
  model** to `require_permission()` as if it were a FastAPI Request.
  All now use a real `Request` plus a separate validated body.
- **Tenant and role forgery:** AI chat ignored neither client-submitted
  tenant nor prompt role reliably; classify and learning accepted the
  caller's tenant_id. New routes take the Tenant from the verified JWT,
  request and active database context; prompt role comes from signed auth.
  Classification/learning body tenant fields are overwritten safely.
  Learning mutations require `patterns:manage`; the vector write
  side path is deliberately disabled pending tenant isolation.
- **AI write bypass:** `chat:use` alone formerly reached draft creation
  via file analysis or implicit posting intents. Draft-generating AI
  operations now demand additional `posting:write` permission before
  handling user data. Unprivileged chatbot roles cannot create drafts.
- **Session collision:** The LLM in-process cache previously indexed
  sessions by session_id alone, regardless of Tenant. It now indexes
  (tenant_id, session_id). All new /api/ai/chat persistent session
  references use a deterministic, opaque per-Tenant/per-User scoped ID
  `usr2_...`. That scoped ID is used consistently for session metadata,
  export and deletion, while the client-facing session ID stays unchanged.
  **Historical rows are preserved, NOT deleted or automatically reused.**
  Access to old unscoped session rows requires a separately authorized
  safe ownership migration; automatically reattaching them would risk
  user-to-user disclosure. Durable multi-replica behavior still requires
  actual staging verification.
- **Global vector read/file scan:** Existing Chroma learned rules are
  queried without per-Tenant filters. New AI chat/search disallow that
  shared vector lookup; keyword-only general KB search remains available
  to authenticated users. Remote `/api/ai/index` filesystem traversal
  and `/api/ai/vector-stats` are explicitly unavailable (503) even to
  authorized users until tenant-aware indexing, metadata filters, grants
  and an isolated staging test are verified. No old indexes or files
  were removed or reindexed.
- **Data exposure:** Stats no longer trigger a global learned-rule scan
  nor report shared vector/learned record counts. Sensitive approval
  preview reads require `approval:read` in addition to chat scope.
  Tool errors return sanitized text and log only exception type rather
  than revealing DB/provider error details.
- **Orchestrator financial parity:** The separate `financial_summary`
  tool still calculated revenue/expenses from approved/auto_approved
  drafts rather than canonical P&L. It now invokes
  `financial_statements_service.build_profit_and_loss(tenant_id)`
  (same as /reports/pnl), preserves approved draft counts only as
  workflow KPIs, and withholds financial totals if source unavailable.
  Its tax tool now restricts credits to POSTED drafts and explicitly
  disclaims that these are reconciled tax liabilities.

## 2. Exact synthetic CI evidence on code SHA above

- [Disposable PostgreSQL 15/16](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40870151968):
  **364 passed each** (real isolated nonowner forced RLS fixtures plus
  AI RBAC negatives; no Production/Cloud SQL).
- [Full backend + frontend + smoke](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40870151999):
  **8,214 backend passed, 3 skipped**, smoke **1 passed**,
  frontend build SUCCESS; **Cloud Run deploy SKIPPED**.
- [Disposable Redis 7](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40870151989):
  210 test suite PASS; shared fail-closed rate limiter.
- [NEXT-01 tenant membership](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40870152053):
  PASS.
- [NEXT-04A financial RLS](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40870151971):
  PASS.
- Regression tests: `tests/unit/test_chat177_ai_api_tenant_guard.py`
  covers anonymous/role denial, untrusted tenant/role inputs, user/tenant
  session isolation and exports, safe calculator request signatures,
  mutation authorization, disabled vector/index paths, tool parity,
  redacted errors and no cross-tenant LLM cache hits. Existing
  `test_p0_ai_action_confirm.py` fixtures were updated for signed
  context without weakening the production guard.

## 3. Still blocked / next isolated stage

- **No live JWT/browser or Cloud Run staging tests.** Verify true
  middleware sequencing, existing clients' role/session ID compatibility,
  new user-scoped session persistence across replicas, old-row ownership
  migration, all file upload paths and OAuth user/tenant membership.
- Rebuild the Chroma vector read/indexing design with explicit per-Tenant
  metadata filters, owner-scoped data sources, private GCS policy and
  cross-tenant negative tests before any reactivation.
- Evaluate global KB files and AI tools for further tenant-sensitive
  content. Full provider LLM data flow requires a separately authorized,
  synthetic-only staging E2E.
- **Accounting:** Production posted-ledger feature flag is NOT enabled.
  The earlier two-Tenant parity proof uses legacy posted drafts. Canonical
  immutable journal-entry parity under real staging migrations, report
  reconciliation, AI audits and export calculations remain pending.
- **Recovery and P0:** Cloud SQL current backup/PITR and isolated clone
  restore, role/owner bypass, migrations 013-016, Redis failover and proxy,
  regional JWT parity, real OAuth/SMTP, GCS attachment recovery and Windows
  original integrity are NOT certified.
- Production HOLD. PR #154 OPEN/DRAFT. Owner authorization separately
  required before staging deploy, runtime config, main merge or Production.
