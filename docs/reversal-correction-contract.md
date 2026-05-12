# Bridge Hub — Reversal / Correction Contract

**Task:** 11C-H9
**Type:** Contract document and tests only — no runtime code change, no SQL, no migration execution.
**Date:** 2026-05-13
**Follows:** 11C-H8 `tests/unit/test_reports_posted_ledger_query_mock_contract.py`

---

## 1. Purpose

Posted ledger entries in `journal_entry_headers` and `journal_entry_lines` must **never** be destructively edited or deleted. All accounting errors, overstatements, or posting mistakes must be resolved through **append-only accounting events** — reversal entries and correction entries — that preserve the original immutable record while creating a complete, auditable trail.

This contract defines the rules for how reversal and correction must be represented in the Bridge Hub ledger. No runtime implementation is changed by this task. This contract is the specification that H13 will mock-test and H14 will implement once explicitly approved.

**No SQL is executed in this task. No production DB is touched. No migration is executed. No runtime posting, approval, or report behavior is changed.**

---

## 2. Purpose — Accounting Principle

The immutability requirement follows from the core accounting truth principle established in H2–H5:

> **Once a real ERP connector posting is confirmed and written to `journal_entry_headers`, that record is permanent accounting history.**

Any correction to an error in a posted entry must:
1. Leave the original entry intact and readable.
2. Represent the correction as one or more new ledger entries.
3. Preserve the full audit trail from original entry to reversal/correction.
4. Allow reports to produce both a **net official view** (excluding reversed originals) and a **history/audit view** (full chain).

---

## 3. Background

The H1–H8 foundation that makes this contract necessary:

| Task | Deliverable |
|---|---|
| H1 | Reports ledger integrity audit — CRITICAL: no immutable `journal_entries` table; reports source from `journal_drafts` JSONB |
| H2 | Posted journal entries schema contract — defined `journal_entry_headers` + `journal_entry_lines` with `reversed_by_entry_id` and `correction_of_entry_id` fields |
| H3 | Safe migration plan — defined constraint requirements, rollout sequence |
| H4 | SQL migration file `011_posted_journal_entries_schema.sql` created but **not executed** |
| H5 | Posting service ledger write contract — defined when and how immutable ledger entries are written |
| H6 | Posting service ledger write mock tests — 59 tests encoding future write rules |
| H7 | Reports posted-ledger read contract — defined reversal/correction handling rules for reports |
| H8 | Report query mock tests — 89 tests for future query rules including reversal/correction exclusion |
| H9 (this task) | Reversal/correction contract — defines the complete append-only reversal and correction model |

Until H13 and H14 are implemented, no reversal or correction writes occur through this system. H9 prepares the behavioral contract so H13 can be mock-tested safely.

---

## 4. Immutable Posted Ledger Rule

The following rules apply permanently to all records in `journal_entry_headers` and `journal_entry_lines`:

1. **No direct UPDATE to accounting fields**: `account_code`, `debit`, `credit`, `amount_gel`, `currency`, `exchange_rate`, `entry_date`, `period`, `total_debit`, `total_credit`, `tenant_id`, and all line fields are immutable after the initial insert.
2. **No DELETE of posted entries**: A posted `journal_entry_headers` row and its associated `journal_entry_lines` rows must never be deleted once committed.
3. **No destructive correction**: A correction to a posting error must not overwrite, nullify, or remove the original entry. All corrections are new rows.
4. **Status can be updated to `reversed`**: The `status` field on `journal_entry_headers` may be updated from `posted` to `reversed` **only** when a reversal entry is created — this is the sole exception to field immutability. No other field may be updated.
5. **`reversed_by_entry_id` and `correction_of_entry_id` may be set**: These link fields may be populated after initial insert to create the reversal/correction chain. No accounting fields change.
6. **Lines are always immutable**: `journal_entry_lines` rows may never be updated or deleted under any circumstances.

---

## 5. Reversal Definition

A reversal is an append-only accounting event that offsets a previously posted entry:

### 5.1 What a reversal creates
- A new `journal_entry_headers` row with `status = 'reversed'` referencing the original entry via `reversal_of_entry_id` (conceptual) or `correction_of_entry_id`.
- New `journal_entry_lines` rows that **invert the debit/credit** of each original line: every original debit becomes a credit and every original credit becomes a debit.
- The new reversal entry is balanced: `total_debit = total_credit`.
- The original entry's `reversed_by_entry_id` is set and `status` updated to `'reversed'`.

### 5.2 Reversal requirements
1. **Original entry must exist** and belong to the same tenant.
2. **Reversal reason is required** — must be a non-empty string recorded in the reversal header metadata.
3. **Reversal must have `tenant_id`** — matching the original entry's `tenant_id`.
4. **Reversal preserves source links** — `source_draft_id`, `evidence_bundle_id`, `posting_log_id` from original may be preserved in the reversal where relevant.
5. **Reversal must create an audit event** — recording actor, timestamp, reason, original entry id, and reversal entry id.
6. **Reversal must not reuse the original entry id** — a new UUID is generated for the reversal entry.
7. **Reversal must be idempotent** — if a reversal for the same original entry already exists (same `reversal_of_entry_id` + `tenant_id`), return the existing reversal entry without creating a duplicate.
8. **Reversal inverts all lines** — partial reversals are not supported by this contract unless explicitly designed as a separate feature.
9. **No raw secrets in reversal metadata** — `_strip_unsafe` must be applied before writing `metadata_json`.

### 5.3 Reversal flow
```
Original posted entry (status='posted')
    │
    ▼
Reversal triggered (actor, reason, original_entry_id)
    │
    ├── Idempotency check: reversal for this entry already exists?
    │       YES → return existing reversal entry id
    │       NO → continue
    │
    ├── Tenant isolation check: original.tenant_id == request.tenant_id?
    │       NO → fail closed
    │
    ├── Status check: original.status == 'posted' or 'correction'?
    │       NO → fail closed
    │
    ├── Period lock check: is_period_locked()?
    │       YES → fail closed (unless reopening policy allows)
    │
    ├── Permission check: actor has reversal permission?
    │       NO → fail closed
    │
    └── Append new reversal entry (inverted lines, balanced)
            │
            ├── UPDATE original: status='reversed', reversed_by_entry_id=new_id
            └── INSERT audit event
```

---

## 6. Correction Definition

A correction is an append-only accounting event that replaces an erroneous posted entry with the correct accounting:

### 6.1 Correction approaches
This contract supports two correction policies — the chosen policy must be explicit in the implementation:

**Policy A: Full reversal + new corrected entry**
1. Create a reversal of the original entry (as per Section 5).
2. Create a new corrected entry with the correct lines, with `correction_of_entry_id` referencing the original.
3. This produces three entries in total: original, reversal, correction.
4. Net view shows only the correction.

**Policy B: Delta correction entry**
1. Create a new correction entry that contains only the difference (delta) lines.
2. The correction entry references the original via `correction_of_entry_id`.
3. The original remains `status='posted'` — it is not set to `'reversed'`.
4. Net view includes original + delta correction.
5. Used when partial adjustment is required without full reversal.

### 6.2 Correction requirements
1. **Original entry must exist** and belong to the same tenant.
2. **Correction reason is required** — must be a non-empty string.
3. **Correction must have `tenant_id`** — matching the original.
4. **Correction preserves evidence/source links** where applicable.
5. **Correction must create an audit event** — recording actor, timestamp, reason, original entry id, and correction entry id.
6. **Correction must be idempotent** — if a correction for the same original + correction_policy already exists, return the existing correction entry without creating a duplicate.
7. **Correction policy must be explicit** — Policy A or Policy B must be stated at time of correction request.
8. **No raw secrets in correction metadata**.
9. **Original entry must never be mutated** by the correction process.

---

## 7. When Reversal / Correction Is Allowed

A reversal or correction is allowed **only when ALL of the following are true**:

1. Original entry exists in `journal_entry_headers`.
2. Original entry `tenant_id` matches the authenticated request tenant.
3. Original entry `status` is `'posted'` or `'correction'` (per policy).
4. The accounting period is **not locked** (`is_period_locked` returns false), or an explicit period reopening policy permits the action.
5. The requesting actor has the required **reversal/correction permission** (e.g., `ledger:reverse` or `ledger:correct`).
6. A **non-empty reason** is provided.
7. The resulting reversal/correction lines are **balanced** (`total_debit = total_credit`).
8. An **audit/evidence trail** can be created.
9. No duplicate reversal/correction already exists for the same **idempotency key** (original entry id + action type + tenant_id).
10. The action does **not** mutate or delete any existing posted lines.
11. No raw credentials/secrets are present in metadata.

---

## 8. When Reversal / Correction Is Forbidden

A reversal or correction must be **explicitly refused** when any of the following are true:

| Condition | Reason |
|---|---|
| Original entry missing | Cannot reverse/correct what does not exist |
| `tenant_id` mismatch | Tenant isolation violation |
| Original entry status is `draft` | Not a real posting — cannot be reversed |
| Original entry status is `approved` | Not yet posted — not a ledger entry |
| Original entry status is `auto_approved` | Not a real posting |
| Original entry status is `simulated_success` | Test/simulation state — no real ERP entry |
| Original entry status is `mock_posting` | Development artifact |
| Original entry status is `dry_run` | Preview mode — not a real posting |
| Original entry status is `voided` | Already voided — cannot be reversed again |
| Original entry already `reversed` (for reversal) | Already reversed — idempotent return, not re-reversal |
| Period is locked and no reopening policy | `is_period_locked` returns true |
| Reversal/correction lines are unbalanced | `sum(debit) ≠ sum(credit)` |
| Reason missing or empty | Audit trail incomplete |
| Actor lacks required permission | RBAC violation |
| Duplicate idempotency key | Already exists — return existing, do not duplicate |
| Action would mutate existing posted lines | Immutability violation |
| Raw secrets in metadata | Security violation |

---

## 9. Report Behavior

Official reports must handle reversals and corrections consistently:

### 9.1 Net official view (standard reports)
- **Trial Balance, P&L, Balance Sheet**: exclude entries where `status='reversed'`. Include `status='posted'` and `status='correction'`.
- **No double-counting**: if an original entry is reversed and a correction exists, only the correction (and any subsequent reversal if applicable) appears in the net total.
- **Voided entries** are excluded from all net official totals.

### 9.2 History / audit view
- Includes the full reversal/correction chain: original (`status='posted'`), reversal (`status='reversed'`), and correction (`status='correction'`) entries.
- Accessible via audit/history query mode only — not default report behavior.
- Must show actor, reason, and timestamp for each event in the chain.

### 9.3 Report rules
- Reports must not double-count an original entry and its correction when both are included.
- Reports must preserve the audit trail of reversal/correction chains.
- Trial Balance, P&L, Balance Sheet, Account Ledger, Counterparty Ledger, VAT Register, Payroll Ledger, and Journal Entries List must all respect the `status='reversed'` exclusion in net view.
- Reports may expose reversal/correction details in a dedicated history column or drill-down view.

---

## 10. Data Model Requirements

The following conceptual fields are required on `journal_entry_headers` to support the reversal/correction model. These fields are already included in the H4 SQL migration contract:

| Field | Purpose |
|---|---|
| `reversed_by_entry_id` | UUID of the reversal entry that reversed this entry (nullable) |
| `correction_of_entry_id` | UUID of the original entry this correction is based on (nullable) |
| `reversal_reason` | Non-empty reason text for reversal (stored in `metadata_json` or dedicated field) |
| `correction_reason` | Non-empty reason text for correction |
| `correction_policy` | `'full_reversal'` or `'delta'` — explicit policy |
| `idempotency_key` | Composite key: `original_entry_id + action_type + tenant_id` |
| `audit_event_id` | Reference to audit event created for this reversal/correction |
| `evidence_bundle_id` | Link to supporting evidence bundle (nullable) |
| `metadata_json` | Non-financial metadata — must be stripped of secrets via `_strip_unsafe` |
| `created_by` | Actor who initiated the reversal/correction |
| `approved_by` | Actor who approved (if approval gate exists for reversals) |
| `posted_by` | System or actor that executed the ledger write |
| `created_at` | Timestamp of entry creation |
| `posted_at` | Timestamp of connector confirmation (for correction entries that go through connector) |

---

## 11. Audit and Evidence

1. **Every reversal/correction must create an audit event** in the `audit_log` table — recording: actor, timestamp, action type (`reversal` or `correction`), reason, original entry id, new entry id, tenant_id.
2. **Reason and actor must be recorded** — missing reason or actor is a contract violation.
3. **`evidence_bundle_id` should link to supporting evidence** where available — reversal decisions based on documents should include evidence links.
4. **`posting_log_id` should link if a connector action is involved** — corrections that trigger a new ERP posting must link to the new `posting_log` entry.
5. **No raw credentials/secrets in metadata/evidence/audit** — `_strip_unsafe` from `evidence_bundle_service.py` must be applied before writing `metadata_json` on any reversal/correction header. Fields `api_key`, `password`, `token`, `secret`, `encrypted_value` must never appear in ledger metadata.
6. **Audit trail must be complete** — the chain from original entry to reversal to correction must be reconstructable from the `reversed_by_entry_id` and `correction_of_entry_id` fields.

---

## 12. Non-Goals for H9

This task explicitly does **not**:

- Change any runtime reversal or correction behavior.
- Modify `posting_service.py`.
- Modify `approval_service.py`.
- Modify `ledger_service.py`.
- Modify `financial_statements_service.py`.
- Modify `routes_reports.py` or `routes_posting.py` or any route handler.
- Execute any SQL.
- Create any new SQL migration file.
- Execute any migration.
- Access any database (production or otherwise).
- Touch the production database.
- Change any connector behavior.
- Activate Balance.ge.
- Change any credentials or secrets.
- Change any production infrastructure or deployment configuration.
- Start H10, H11, H12, H13, or H14 work.

This task produces two files only:
- `docs/reversal-correction-contract.md` (this document)
- `tests/unit/test_reversal_correction_contract.py`

---

## 13. Future Task Sequence

| Task | Description |
|---|---|
| **H9** (this task) | Reversal / correction contract / tests only — no runtime change |
| **H10** | Evidence / audit export linkage contract — define how `evidence_bundle_id` links to posted entries and how audit export should work |
| **H11** | Controlled local/test migration execution plan — if explicitly approved, run `011_posted_journal_entries_schema.sql` against a local or test DB only; never production without separate approval |
| **H12** | Runtime report migration plan — migrate reports to read from posted ledger tables after H11 migration is confirmed |
| **H13** | Reversal/correction implementation tests with mocks — mock-test the future `_write_reversal_entry` and `_write_correction_entry` functions |
| **H14** | Reversal/correction runtime implementation — only after H13 tests pass and explicit stakeholder approval |

Each task follows the same protocol: branch → docs/tests → PR → merge → deploy → live verification → confirmed before starting the next task.

---

*Bridge Hub — Task 11C-H9. Contract only. No runtime changes. No SQL. No migration execution. No production DB touch. Balance.ge remains inactive.*
