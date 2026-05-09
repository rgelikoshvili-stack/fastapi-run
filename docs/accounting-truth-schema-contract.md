# Accounting Truth Schema Contract

## Purpose

Task 10E-D defines the accounting truth schema contract before any accounting truth migrations or runtime behavior changes.

This task is contract and test coverage only:

- It does not create migrations.
- It does not edit runtime app code.
- It does not change approval behavior.
- It does not change posting behavior.
- It does not change reporting behavior.
- It does not activate Balance.ge.
- It does not execute SQL.
- It does not touch production databases.

## Accounting Truth Objects Covered

This contract applies to:

- `journal_drafts`
- `draft_comments`
- `journal_entries`
- `journal_lines` if present or planned
- `posting_logs`
- `posting_queue` if present or planned
- `audit_events`
- `approval_history`
- `period_locks`
- `bank_reconciliations` when tied to posted accounting state
- any reporting source table used as accounting truth

## Approval-First Workflow

Bridge Hub must preserve an approval-first accounting workflow:

- AI may create draft proposals only.
- AI must not post directly.
- Posting requires an approved draft.
- Connector execution requires an approved accounting action or approved draft.
- High-risk or large-amount drafts require configured approval policy.
- CFO or second-level approval must be supported for configured thresholds.
- Corrections must preserve history.
- Rejections must preserve reviewer reason and timestamp.
- Batch approval must preserve per-item results and failures.

Accounting-impacting modules such as inventory, payroll, trade, document OCR, bank reconciliation, AI chat, and connector flows must create drafts or proposals first. They must not write directly to posted ledger truth.

## Posted-Only Ledger Truth

Final ledger truth must come from posted sources only:

- Reports must use posted `journal_entries` or explicitly approved/posting-complete sources.
- Drafts must not appear in final ledger reports unless clearly marked as draft or pro forma.
- Trial balance must distinguish draft turnover from posted turnover.
- Income statement must distinguish draft results from posted results.
- Balance sheet must distinguish draft balances from posted balances.
- VAT reports must distinguish draft VAT exposure from posted VAT truth.
- Cash flow and close dashboards must label non-posted operational views clearly.

`journal_drafts` can support review, preview, and pro forma reporting. It must not be silently treated as posted ledger truth.

## Immutability and Reversal

Posted accounting truth must be immutable or reversed through explicit reversal entries:

- Posted `journal_entries` must not be edited in place for accounting corrections.
- Corrections after posting must create reversal and replacement entries.
- Reversal entries must reference the original entry or source draft.
- Posted rows should preserve created metadata, source evidence, and posting target.
- Destructive correction of posted truth is forbidden.

If legacy tables currently allow mutation, future hardening must introduce safe reversal workflows before real accounting use.

## Posting Logs

`posting_logs` must preserve connector and posting attempts without secrets:

- tenant ID
- source draft ID
- target connector/system
- idempotency key or entry hash
- request payload summary or safe payload copy
- response payload summary or safe response copy
- status
- error code
- error message with no secrets
- timestamps
- actor or system initiator

Posting logs are audit evidence. They must not store plaintext credentials, API keys, session tokens, webhook secrets, TOTP secrets, or password reset tokens.

## Audit Trail and Reviewer History

`audit_events`, `approval_history`, and `draft_comments` must preserve who, what, when, and why:

- who created a draft
- who changed a draft
- who approved or rejected
- who posted or attempted posting
- what fields changed
- why a correction or rejection happened
- source evidence references
- status transition history
- reviewer notes

Audit records should be append-only where practical. If updates are required for operational metadata, they must not erase decision history.

## Idempotency

Posting must be idempotent by tenant and target:

- tenant ID
- draft ID
- connector or target system
- idempotency key
- entry hash or equivalent deterministic posting fingerprint

Duplicate posting attempts must be rejected or return the existing result safely. Connector retries must not create duplicate ledger entries. Idempotency records must include enough data to explain whether the operation was new, repeated, skipped, or already completed.

## Tenant Isolation

Tenant-owned accounting truth tables must include `tenant_id`.

Required rules:

- All accounting queries must be tenant-scoped.
- All reporting queries must be tenant-scoped.
- Posting logs must be tenant-scoped.
- Audit events must be tenant-scoped.
- Period locks must be tenant-scoped.
- Reconciliation records must be tenant-scoped.
- Global tables must be explicitly documented as global.

Future migrations should include indexes for tenant/date/status lookups where relevant.

## Period Lock and Cut-Off

Approval and posting transitions must respect period locks:

- Posting into locked periods must be blocked unless an explicit policy allows controlled reopening.
- Backdated entries require explicit policy and audit trail.
- Period locks must record who locked or unlocked, when, and why.
- Close-period workflows must not mutate posted truth destructively.
- Close workflows may create previews, checklists, reports, and lock records.
- Unlocking a period must be auditable.

Period lock checks must protect posting, connector execution, and final ledger truth.

## Accounting Evidence

Every posted entry should be traceable to source evidence:

- document
- bank transaction
- manual entry
- payroll run
- inventory movement
- sales invoice
- purchase order
- connector payload
- approval event
- reviewer comment
- AI decision explanation

An evidence bundle is required before any Balance.ge or ERP write pilot. The evidence bundle should include source files, extracted fields, AI reasoning, validation warnings, reviewer decision, posting payload, and posting result.

## Reporting Source Rules

Reporting modules must document which source they use:

- final ledger report
- draft/pro forma report
- operational queue
- close checklist
- tax review

Trial balance, income statement, balance sheet, VAT reports, and close reports must not silently mix draft and posted data. If draft data is included for preview, the response and UI must label it clearly.

## No Destructive Migrations

Future accounting truth migrations must be additive-only:

- `CREATE TABLE IF NOT EXISTS`
- `CREATE INDEX IF NOT EXISTS`
- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- no `DROP TABLE`
- no `TRUNCATE`
- no data-destructive `DELETE`
- no data-rewriting `UPDATE` migration without a separate reviewed data plan
- no destructive `ALTER`
- no production DB mutation during planning/contract tasks

Runtime DDL removal must wait until migration coverage and tests prove safety.

## Implementation Deferral

This task intentionally defers implementation:

- Accounting truth migrations are still implementation work.
- Evidence bundle is still implementation work.
- Runtime DDL removal is still deferred.
- Approval runtime behavior is unchanged.
- Posting runtime behavior is unchanged.
- Reporting runtime behavior is unchanged.
- Connector runtime behavior is unchanged.
- Balance.ge live activation is still deferred.
- Production database is not touched by this task.

## Future Acceptance Criteria

Before real accounting use:

- 100% approval-before-posting.
- 0 AI direct postings.
- Posted ledger reports use posted sources only.
- Draft/pro forma reports are clearly labeled.
- Posted entries are immutable or corrected by reversal.
- Posting is idempotent by tenant, draft, target, and key/hash.
- Posting logs contain no secrets.
- Accounting truth tables are tenant-scoped.
- Period locks block unsafe posting.
- Evidence bundle exists for connector execution.
- Additive migrations cover accounting truth tables before runtime DDL removal.
