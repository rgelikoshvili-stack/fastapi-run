# Subscription / Trial Enforcement Plan

## A) Purpose

Subscription and trial enforcement is required before commercial pilot. Without it,
expired or suspended tenants can freely execute paid actions — creating journal
drafts, posting to connectors, uploading documents, approving ERP entries — with
no payment or active subscription.

This plan defines:

- Tenant lifecycle states and their enforcement rules.
- Which endpoint categories are blocked for each tenant state.
- Connector execution blocking rules.
- Admin override policy.
- Required error codes and API response contract.
- Audit requirements for enforcement events.
- Future implementation scope split into safe sub-tasks.

**This task defines the contract only.**

No runtime behavior is changed in this task. No middleware is edited. No
migration is created. No production database is touched. Balance.ge remains
inactive.

---

## B) Current State

### Completed Trust Foundation work

- `docs/auth-tenant-schema-contract.md` — tenant lifecycle and subscription
  fields defined as a contract.
- `docs/trust-foundation-implementation-plan.md` — Pillar 3 defines subscription
  enforcement as a required trust foundation step.
- `docs/credential-vault-design.md` + `docs/credential-vault-interface-contract.md`
  — credential vault architecture defined.
- `docs/masked-read-behavior-contract.md` — masked read behavior contract defined.

### Runtime state (not changed in this task)

| Item | Current Behavior | Risk |
|---|---|---|
| `tenants.subscription_tier` | Column exists (`TEXT DEFAULT 'trial'`). Set to `'trial'` at signup. **Never checked** in any middleware or route. | High |
| `tenants.trial_ends_at` | Column exists (`TIMESTAMPTZ`). Set to `now() + 14 days` at signup. **Never checked**. An expired trial tenant can execute any action indefinitely. | Critical |
| `tenants.status` | Column exists. Set to `'active'` at signup. **Never enforced**. | High |
| `app/api/middleware/auth_middleware.py` | JWT validation only. No subscription/trial check. | Critical |
| `app/api/middleware/rbac_middleware.py` | Role/permission check only. No tenant state check. | Critical |
| Login response | Returns `subscription_tier` from DB. Not enforced. | Medium |

**Runtime behavior: unchanged in this task.**
**Balance.ge activation status: inactive — Balance.ge must stay inactive.**
**Production DB status: untouched in this task.**
**No migration is created in this task.**

---

## C) Tenant Lifecycle States

Bridge Hub tenants may be in one of the following states:

| State | Description | Enforcement Level |
|---|---|---|
| `active` | Paying, active subscription. Full access according to RBAC. | Full |
| `trial` | Within trial period (`trial_ends_at` not yet passed). Limited access per pilot scope. | Limited |
| `trial_expired` | Trial period has passed. Not yet suspended. Blocked from paid/mutating actions. | Blocking |
| `suspended` | Admin-suspended tenant. Blocked from most or all actions by policy. | Blocking |
| `expired` | Subscription expired (past grace period). Blocked from mutating/connector actions. | Blocking |
| `inactive` | Archived, cancelled, or deactivated. All tenant-scoped access blocked except admin recovery. | Full Block |

### Transition Rules

- `trial` → `trial_expired`: automatic when `trial_ends_at` is passed and no subscription payment made.
- `trial_expired` → `active`: on subscription payment/renewal.
- `active` → `suspended`: by admin action (abuse, billing failure, policy).
- `active` → `expired`: when subscription period lapses without renewal.
- `suspended` → `active`: by admin reactivation (audited).
- `expired` → `active`: on subscription renewal.
- Any state → `inactive`: by admin archival action (audited).

---

## D) Enforcement Policy

### active

- Read allowed.
- Write allowed according to RBAC.
- Connector execution allowed only if connector gates pass (e.g. Balance.ge
  activation requires all 12 gates in `docs/balance-ge-activation-gate.md`).

### trial

- Read allowed.
- Write allowed according to RBAC within allowed pilot scope.
- Connector execution allowed only in explicitly marked safe/free pilot scope.
- Usage limits may apply per tenant plan (e.g. document upload count).
- Connector live execution (Balance.ge, ORIS, RS.ge submit) blocked until trial
  scope explicitly enables it.

### trial_expired

- Read allowed (reports, exports, billing/renewal page).
- Exports allowed for own data during grace period per policy.
- Mutating writes blocked: no journal drafts, no document processing, no invoice
  creation, no payroll, no inventory, no trade records.
- Approval and posting blocked.
- Connector execution blocked.
- Error code required: `TENANT_TRIAL_EXPIRED` with renewal link or message.

### suspended

- Read-only or fully blocked depending on admin policy at suspension time.
- Mutating writes blocked.
- Connector execution blocked.
- Approval and posting blocked.
- Error code required: `TENANT_SUSPENDED`.
- Suspension reason must be logged in audit.

### expired

- Read allowed for billing/grace/export policy only.
- Mutating writes blocked.
- Connector execution blocked.
- Approval and posting blocked.
- Error code required: `TENANT_SUBSCRIPTION_EXPIRED`.

### inactive

- All tenant-scoped access blocked except admin recovery path.
- Error code: `TENANT_INACTIVE`.
- Recovery requires explicit admin action, audited.

---

## E) Endpoint Categories

All Bridge Hub routes are classified into these enforcement categories:

| Category | Examples | Blocked for trial_expired/suspended/expired? |
|---|---|---|
| `public` | `/health`, `/version`, `/docs`, `/static/*` | No — always accessible |
| `auth_session` | `/auth/login`, `/auth/register`, `/auth/refresh`, `/auth/signup` | No — required for renewal/recovery |
| `read_only_reporting` | `/reports/*`, `/financial-statements/*`, `/audit-trail/*` | No — allowed for data access/export |
| `document_processing` | `/documents/upload`, `/ocr/*`, `/bank-csv/*`, `/email-collector/*` | Yes — blocked |
| `draft_creation` | `/approval/create`, `/ai-journal/*`, `/transaction-ai/*` | Yes — blocked |
| `approval` | `/approval/approve`, `/approval/reject`, `/approval/queue` writes | Yes — blocked |
| `posting_connector_execution` | `/posting/*`, `/balance-ge/*`, `/1c/*`, `/erp-connectors/*` | Yes — blocked |
| `credential_management` | `/balance-credentials/save`, `/rsge-credentials/save`, `/email-collector/save` | Yes — blocked |
| `tenant_admin_billing` | `/tenants/*`, `/billing/*`, `/settings/*` | Partial — billing/renewal allowed |
| `exports` | `/export/*`, `/reports/export/*`, `/payroll/slip/*` | Limited — own data export may be allowed |

---

## F) Mutating Endpoint Blocking

Future enforcement must block `trial_expired`, `suspended`, and `expired` tenants
from the following actions:

| Action | Route Category | Error Code |
|---|---|---|
| `create_journal_draft` | draft_creation | `TENANT_WRITE_BLOCKED` |
| `upload_document` | document_processing | `TENANT_WRITE_BLOCKED` |
| `approve_draft` | approval | `APPROVAL_BLOCKED_BY_SUBSCRIPTION` |
| `reject_draft` | approval | `APPROVAL_BLOCKED_BY_SUBSCRIPTION` |
| `post_to_connector` | posting_connector_execution | `CONNECTOR_BLOCKED_BY_SUBSCRIPTION` |
| `save_credentials` | credential_management | `CREDENTIAL_CHANGE_BLOCKED_BY_SUBSCRIPTION` |
| `test_connector` | posting_connector_execution | `CONNECTOR_BLOCKED_BY_SUBSCRIPTION` |
| `update_tenant_settings` | tenant_admin_billing | `TENANT_WRITE_BLOCKED` |
| `create_invoice` | document_processing / trade | `TENANT_WRITE_BLOCKED` |
| `create_payroll` | draft_creation | `TENANT_WRITE_BLOCKED` |
| `create_inventory` | draft_creation | `TENANT_WRITE_BLOCKED` |
| `create_trade_record` | draft_creation | `TENANT_WRITE_BLOCKED` |

All blocked responses must use the standard error envelope:

```json
{
  "ok": false,
  "message": "Trial has expired. Please renew your subscription.",
  "data": null,
  "error": {
    "code": "TENANT_TRIAL_EXPIRED",
    "details": "Mutating actions are blocked for expired trial tenants."
  }
}
```

Blocked responses must not expose raw credentials, secrets, or tenant data
beyond the error code and a safe human-readable message.

---

## G) Read-only Access Policy

The following access remains allowed for `trial_expired`, `suspended`, and
`expired` tenants unless further restricted by admin policy:

- `/health`, `/version` — always allowed.
- Billing/subscription status and renewal page — always allowed.
- Read-only reports: trial balance, P&L, balance sheet (for data portability).
- Export own accounting data (`/export/*`) — allowed during grace period per policy.
- Audit history read — allowed.
- Login and session refresh — allowed (required for renewal flow).

The specific grace period duration and data portability window are implementation
decisions to be made during Task 10F-D2 (tenant status service).

---

## H) Connector Execution Blocking

For `trial_expired`, `suspended`, and `expired` tenants, the following connector
execution paths must be blocked:

| Connector / Action | Block Condition | Error Code |
|---|---|---|
| `balance_posting` | trial_expired, suspended, expired | `CONNECTOR_BLOCKED_BY_SUBSCRIPTION` |
| `oris_posting` | trial_expired, suspended, expired | `CONNECTOR_BLOCKED_BY_SUBSCRIPTION` |
| `one_c_posting` | trial_expired, suspended, expired | `CONNECTOR_BLOCKED_BY_SUBSCRIPTION` |
| `rsge_submit` | trial_expired, suspended, expired | `CONNECTOR_BLOCKED_BY_SUBSCRIPTION` |
| `email_send` | trial_expired, suspended, expired (if paid feature) | `CONNECTOR_BLOCKED_BY_SUBSCRIPTION` |
| `connector_test` | trial_expired, suspended, expired | `CONNECTOR_BLOCKED_BY_SUBSCRIPTION` |
| `dry_run` | Only if explicitly marked free/safe in pilot scope | May be allowed |

Note: Balance.ge is currently inactive and requires all 12 gates in
`docs/balance-ge-activation-gate.md` to be MET before any live execution,
regardless of subscription state.

---

## I) Admin Override Policy

Admin override allows a system administrator to grant temporary access to a
blocked tenant. Rules:

1. Admin override must be **explicit** — no silent bypass.
2. Override must be **time-limited** — a specific duration or expiry timestamp.
3. Override must be **audited** — actor, reason, duration, affected tenant,
   timestamp all recorded in audit log.
4. **Reason required** — admin must supply a reason string at override creation.
5. **Actor required** — override must be tied to an authenticated admin actor.
6. Override **cannot bypass**:
   - Credential safety (raw secrets still must not be exposed).
   - Approval flow safety (human approval still required for ERP actions).
   - Balance.ge activation gate (all 12 gates still required).
7. Override scope must be explicit — it may grant specific endpoint categories
   only, not blanket full access.
8. Override expiry must be enforced — expired overrides must behave as if no
   override exists.
9. `ADMIN_OVERRIDE_REQUIRED` error code indicates an action requires admin
   override to proceed (not that override is already granted).

---

## J) Error Codes / API Contract

Required error codes for subscription enforcement:

| Code | Condition | HTTP Status |
|---|---|---|
| `TENANT_TRIAL_EXPIRED` | Trial period has lapsed, no active subscription | 402 |
| `TENANT_SUBSCRIPTION_EXPIRED` | Paid subscription expired, past grace period | 402 |
| `TENANT_SUSPENDED` | Tenant suspended by admin | 403 |
| `TENANT_INACTIVE` | Tenant archived/deactivated | 403 |
| `TENANT_WRITE_BLOCKED` | Generic mutating action blocked by subscription state | 402 |
| `CONNECTOR_BLOCKED_BY_SUBSCRIPTION` | Connector execution blocked | 402 |
| `APPROVAL_BLOCKED_BY_SUBSCRIPTION` | Draft approval/posting blocked | 402 |
| `CREDENTIAL_CHANGE_BLOCKED_BY_SUBSCRIPTION` | Credential save/change blocked | 402 |
| `ADMIN_OVERRIDE_REQUIRED` | Action requires admin override | 403 |

All error responses must:

- Use the standard Bridge Hub error envelope (`ok: false`, `error.code`, `error.details`).
- Include a human-readable `message` pointing to renewal or support.
- Not expose raw credentials, tenant data, or system internals.
- Not expose `trial_ends_at` as a raw timestamp in error bodies (use relative
  phrasing: "expired N days ago" or simply "expired").

---

## K) Audit Rules

The following events must create audit records when subscription enforcement is
active:

| Event | Audit Required |
|---|---|
| Trial expired block — mutating action blocked | Yes |
| Subscription expired block — mutating action blocked | Yes |
| Suspended tenant block | Yes |
| Inactive tenant block | Yes |
| Admin override used | Yes |
| Connector execution blocked | Yes |
| Approval/posting blocked | Yes |
| Credential change blocked | Yes |
| Tenant status changed (trial → expired, etc.) | Yes |
| Subscription renewed or reactivated | Yes |
| Admin override created | Yes |
| Admin override expired | Yes |

Each audit record must include:

- `actor` (user_id or system identifier)
- `tenant_id`
- `action` (event name above)
- `result` (`ok`, `blocked`, `overridden`)
- `timestamp`
- `safe_error_code` if applicable
- `reason` if admin override

Each audit record must NOT include raw secrets, passwords, tokens, or
credential values.

---

## L) Test Strategy

Task 10F-D tests in `tests/unit/test_subscription_enforcement_contract.py`
validate this contract using only:

- Reading doc files and asserting required content.
- Local test-only state definitions and pure helper functions.
- Assertions on tenant state sets, endpoint categories, error codes.
- No DB access, no runtime imports, no SQL.

Future implementation tests (not in this task):

- `10F-D1`: Enforcement helper/interface tests — pure function tests for
  `is_action_allowed(tenant_state, action_category)`.
- `10F-D2`: Tenant status service — tests for `get_tenant_state()` reading from
  DB mock and returning correct lifecycle state.
- `10F-D3`: Middleware dry-run mode — log-only enforcement without blocking,
  for safe rollout validation.
- `10F-D4`: Mutating endpoint blocking — integration tests asserting 402/403
  for blocked endpoints.
- `10F-D5`: Connector execution blocking — integration tests for connector paths.
- `10F-D6`: Admin override audit — tests for override creation, expiry, and
  audit event generation.
- `10F-D7`: Live verification — staging-level verification of enforcement.

---

## M) Future Implementation Scope

Future implementation tasks for subscription enforcement (after all 10F planning
tasks are merged and approved):

### Task 10F-D1 — Enforcement Helper and Interface Tests

- Create `app/api/services/subscription_enforcement.py` (or equivalent).
- Define `get_tenant_state(tenant_id) → TenantState` interface.
- Define `is_mutating_action_allowed(state, action_category) → bool`.
- Define `is_connector_allowed(state, connector) → bool`.
- Unit tests with mocked DB: trial_expired → blocked, active → allowed.

### Task 10F-D2 — Tenant Status Service

- Implement `get_tenant_state()`: read `subscription_tier`, `trial_ends_at`,
  `status` from `tenants` table; derive current lifecycle state.
- Handle: `trial` (within period), `trial_expired` (past date), `suspended`,
  `expired`, `inactive`, `active`.
- Unit tests: each state transition covered.

### Task 10F-D3 — Middleware Dry-Run / Log-Only Mode

- Add subscription check to middleware in log-only (non-blocking) mode first.
- Feature flag: `SUBSCRIPTION_ENFORCEMENT=log_only | enforce | off`.
- Metrics/logs: count would-be blocks without actually blocking.
- Deploy to staging; validate no false positives.

### Task 10F-D4 — Mutating Endpoint Blocking

- Switch `SUBSCRIPTION_ENFORCEMENT=enforce` after dry-run validation.
- Unit + integration tests for all blocked endpoint categories.
- Confirm 402 for trial_expired, suspended, expired across mutating routes.

### Task 10F-D5 — Connector Execution Blocking

- Add subscription check to connector execution paths.
- Block `balance_posting`, `oris_posting`, `one_c_posting`, `rsge_submit`,
  `email_send`, `connector_test` for blocked states.

### Task 10F-D6 — Admin Override Audit

- Implement admin override creation, expiry, and audit event generation.
- Tests: override grants access, expired override is rejected, reason is required.

### Task 10F-D7 — Live Verification

- Full staging round-trip: trial tenant expires, hits 402, renews, full access
  restored.
- Connector execution blocked for expired tenant, unblocked after renewal.

---

## N) Explicit Non-Goals (This Task)

The following are explicitly deferred and must NOT be implemented in this task:

- No runtime behavior change.
- No middleware edit (`auth_middleware.py`, `rbac_middleware.py` not changed).
- No migration or DDL change (columns already exist from prior runtime DDL).
- No service implementation.
- No connector change.
- No auth or RBAC change.
- No Balance.ge activation.
- No production DB touch.
- No commercial pilot activation.

**Balance.ge activation remains blocked** until all 12 gates in
`docs/balance-ge-activation-gate.md` are MET. All gates are currently NOT MET.

**No migration is created in this task.**

**No runtime code is changed in this task.**
