# Bridge Hub — Chat176 AI financial truth / tenant-isolated chat gate

**Date:** 2026-10-29. **Scope:** Draft PR #154 only. **Production: HOLD.**
**Last fully CI-verified implementation SHA:** `e502014410ce090687c7ac10ee34f840dd255b3e`.

No changes to `main`, Production Cloud Run/SQL/Redis/GCS, JWT secrets,
OAuth providers, Windows originals, local Git index/worktrees/ACLs or live data.
No migration, database DDL or Cloud SQL/GCS restore was run outside the
dedicated disposable GitHub Actions PostgreSQL containers.

## Confirmed findings and Draft-only changes

1. **Legacy /chat session privacy:** `app/api/routes_chat.py` stored chat
   history in a process-wide dictionary keyed only by a caller-provided
   session_id; `/chat/history` lacked an explicit route-level permission
   check, and deleting a session by the same ID could clear another user's
   history. Chat176 checks chat:use AND the signed JWT tenant, current request
   tenant and transaction-local DB tenant plus signed user identity on
   POST /chat/message, GET /chat/history and DELETE /chat/session/{session_id}.
   Sessions are now scoped by (tenant, user, session_id); malformed/oversized
   IDs are denied. Failed upstream calls do not commit partial history and
   never return raw exception details.
   **Residual:** history is still per-process memory, not multi-replica
   durable. A separately approved storage redesign is required for cross-
   replica continuity; the fix proves tenant/user isolation in the local
   process but NOT that sessions persist on Cloud Run.

2. **AI P&L figures disagreed with /reports/pnl:** Previously
   `chat_context_service` computed revenue/expenses from
   approved/auto_approved `journal_drafts`, even though
   `financial_statements_service.build_profit_and_loss` uses POSTED journal
   entries (or the feature-gated immutable posted ledger). AI report
   questions now call exactly the authoritative
   `build_profit_and_loss(tenant_id)` function; source, revenue, COGS+OPEX,
   EBIT and margin derive from that response. On DB/posted-ledger failure the
   prompt explicitly says P&L unavailable rather than inventing a total.
   English and Georgian profit/revenue/expense phrases trigger the canonical
   report. The prior loose approved Draft total in the legacy chat is now
   explicitly labelled a workflow figure, **NOT posted P&L**.

3. **Audit context isolation:** The former audit query included
   `tenant_id IS NULL OR tenant_id = ...`, which could inject unscoped audit
   events into another tenant's AI prompt if DB policy allowed it. Chat176
   demands `tenant_id::text = %s` only and uses actual audit_log schema
   fields (action, resource, resource_id, details), formatted without
   claiming global/null events belong to the tenant.

4. **Natural-language Ask /ask:** Request data now passes
   `require_signed_tenant_permission(chat:use)` before DB execution.
   Revenue/expense and account-code activity query only `status='posted'`,
   no unposted approved drafts, and are clearly labelled **posted draft
   activity, NOT the audited P&L/trial balance**. Advanced transaction
   filters and the legacy account_code query are not falsely represented as
   the canonical ledger summary. Workflow state queries remain separate.

5. **Tax context:** Tax-account credit totals now include only POSTED Drafts,
   and the prompt disclaims that they are **not a tax liability statement**.
   Live tax return reconciliation and ledger parity are separate gates.

## Exact verified disposable CI on implementation SHA

- [PostgreSQL 15 / 16](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40864568494):
  **323 passed on PG15, 323 passed on PG16**. Includes real nonowner
  `NOSUPERUSER NOBYPASSRLS` forced-RLS two-tenant test: canonical /reports/pnl
  and AI context return matching isolated amounts, and approved-but-unposted
  data is excluded. Uses only synthetic entries, no Cloud SQL.
- [Backend/frontend/smoke](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40864568476):
  **8,179 backend passed, 3 skipped**, smoke **1 passed**, frontend PASS;
  real Cloud Run deployment **SKIPPED**.
- [Redis 7](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40864568473):
  PASS (210 suite tests in prior Chat175; do not assume a changed suite count
  without inspecting this run's logs).
- [Tenant membership](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40864568404):
  PASS.
- [Financial RLS](https://github.com/rgelikoshvili-stack/fastapi-run/actions/runs/40864568433):
  PASS.
- A new direct-route synthetic test initially omitted FastAPI's injected
  optional `file=None` and failed due to receiving the File() parameter
  descriptor. The test invocation was fixed, not the security control; all
  checks on the exact code SHA above subsequently passed.

## What remains NOT verified / next Chat177

- **Other AI ingress /api/ai:** audit the broad RBAC public-prefix
  exception, endpoints with only Pydantic request models passed to
  require_permission, caller-submitted tenant IDs in classification/learning,
  optional file indexing and per-route access. Do NOT expose file paths or
  enable remote actions as part of this report. Priority P0/P1 review.
- **Posted-ledger feature switch:** current real-PG parity test explicitly
  uses legacy posted-drafts accounting (`POSTED_LEDGER_REPORTS_ENABLED=0`).
  The feature-gated immutable `journal_entry_headers/lines` path is unit-
  covered in earlier phases but live app parity needs an isolated migration
  011+ staged test before promotion. No production ledger flag was toggled.
- **Actual live policy:** Cloud SQL RLS owners/grants, multi-region JWT
  parity, cross-tenant Bank/AI Audit/Annual report review, real OAuth/SMTP,
  Redis failover and Host/Proxy routing remain unverified in Production.
- **Recovery:** Historical 2026-05-21 Cloud SQL backup/PITR confirmation is
  stale; a full isolated restore clone/GCS attachment restore remains not
  demonstrated. Refer to Chat175 read-only cloudsql backup and catalog
  templates. No production Cloud SQL access occurred in Chat176.
- A real staged user journey must verify /chat API auth, AI orchestration,
  concurrency, malformed metadata, source truth, complete financial reports
  and provider errors without leaking customer information.

**Decision:** Synthetic CI PASS on exact code SHA above.
**Real staging NOT PERFORMED. Production HOLD.** Keep PR #154 OPEN/DRAFT;
no merge, deploy, SQL DDL, Cloud SQL restore, or Windows mutations without
separate explicit owner authorization.
