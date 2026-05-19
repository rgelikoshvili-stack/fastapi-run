-- =============================================================================
-- Bridge Hub — Migration 011
-- Task 11C-H4: Posted Journal Entries Additive Schema Migration
--
-- PURPOSE:
--   Create immutable posted ledger tables:
--     - journal_entry_headers  (one row per confirmed ERP posting)
--     - journal_entry_lines    (double-entry lines per header)
--     - journal_entry_sources  (source/evidence linkage per header)
--
-- REVIEW STATUS:
--   Created in Task 11C-H4. NOT executed by this task.
--
-- EXECUTION:
--   Do not execute manually against production.
--   Future execution must be through the approved migration process only.
--   All statements use IF NOT EXISTS guards and are idempotent.
--
-- SAFETY RULES:
--   - Additive only. Does not remove, modify, or destroy existing data.
--   - Does not touch journal_drafts or any existing table.
--   - Does not change current report runtime behavior.
--   - Does not activate Balance.ge.
--   - Does not backfill data.
--   - Official reports are not changed by this migration file alone.
--   - journal_drafts JSONB remains untouched until later tasks (H5/H6).
--   - Runtime report behavior unchanged — reports still read journal_drafts
--     until H6 migration is implemented and verified.
--
-- ACCOUNTING TRUTH CONTRACT:
--   Only posted journal entries are official accounting truth.
--   status values are restricted to: posted, reversed, correction, voided.
--   draft, approved, auto_approved, simulated_success are forbidden.
--   total_debit must equal total_credit on every header row.
--   Lines are immutable once inserted. Reversals/corrections create new rows.
--
-- CROSS-REFERENCES:
--   docs/posted-journal-entries-schema-contract.md   (H2)
--   docs/posted-journal-entries-migration-plan.md    (H3)
-- =============================================================================


-- =============================================================================
-- A) journal_entry_headers — one immutable row per confirmed ERP posting
-- =============================================================================

CREATE TABLE IF NOT EXISTS journal_entry_headers (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               TEXT            NOT NULL,

    -- Source traceability (soft links — no hard FK to allow independent evolution)
    source_draft_id         UUID            NULL,
    posting_batch_id        TEXT            NULL,
    posting_log_id          UUID            NULL,
    evidence_bundle_id      UUID            NULL,

    -- Accounting dates
    entry_date              DATE            NOT NULL,
    posting_date            TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    period                  TEXT            NOT NULL,

    -- Ledger classification
    status                  TEXT            NOT NULL,
    source_type             TEXT            NOT NULL,
    source_hash             TEXT            NULL,

    -- Currency
    currency                TEXT            NOT NULL DEFAULT 'GEL',
    exchange_rate           NUMERIC(18,8)   NOT NULL DEFAULT 1,

    -- Balancing totals — must satisfy total_debit = total_credit
    total_debit             NUMERIC(18,2)   NOT NULL DEFAULT 0,
    total_credit            NUMERIC(18,2)   NOT NULL DEFAULT 0,

    -- Audit actors
    created_by              TEXT            NULL,
    approved_by             TEXT            NULL,
    posted_by               TEXT            NULL,

    -- Audit timestamps
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    posted_at               TIMESTAMPTZ     NULL,

    -- Reversal and correction linkage (append-only — no destructive edits)
    reversed_by_entry_id    UUID            NULL,
    correction_of_entry_id  UUID            NULL,

    -- Non-financial metadata (connector response summary, etc.)
    metadata_json           JSONB           NOT NULL DEFAULT '{}'::jsonb,

    -- -------------------------------------------------------------------------
    -- Constraints
    -- -------------------------------------------------------------------------

    -- Tenant must be present and non-empty
    CONSTRAINT ck_jeh_tenant_nonempty
        CHECK (tenant_id <> ''),

    -- Only final confirmed ledger states allowed.
    -- draft, approved, auto_approved, simulated_success are forbidden.
    CONSTRAINT ck_jeh_status
        CHECK (status IN ('posted', 'reversed', 'correction', 'voided')),

    -- Source type must be present
    CONSTRAINT ck_jeh_source_type_nonempty
        CHECK (source_type <> ''),

    -- Period must be present
    CONSTRAINT ck_jeh_period_nonempty
        CHECK (period <> ''),

    -- Currency must be present
    CONSTRAINT ck_jeh_currency_nonempty
        CHECK (currency <> ''),

    -- Totals must be non-negative
    CONSTRAINT ck_jeh_total_debit_nonneg
        CHECK (total_debit >= 0),

    CONSTRAINT ck_jeh_total_credit_nonneg
        CHECK (total_credit >= 0),

    -- Double-entry balance invariant: every posted entry must be balanced.
    -- This is the core accounting truth constraint.
    CONSTRAINT ck_jeh_balanced
        CHECK (total_debit = total_credit)
);

COMMENT ON TABLE journal_entry_headers IS
    'Immutable posted ledger headers. One row per confirmed ERP posting. '
    'Only status IN (posted, reversed, correction, voided) is valid. '
    'draft, approved, auto_approved, simulated_success are forbidden. '
    'total_debit must equal total_credit on every row. '
    'Reversals and corrections append new rows — never mutate existing rows. '
    'This migration is additive only. It does NOT change report runtime behavior. '
    'Reports still read journal_drafts until H6 is implemented and verified. '
    'This migration is NOT executed by Task 11C-H4.';

COMMENT ON COLUMN journal_entry_headers.status IS
    'Final ledger state: posted, reversed, correction, voided. '
    'Forbidden values: draft, approved, auto_approved, simulated_success, mock_posting.';
COMMENT ON COLUMN journal_entry_headers.total_debit IS
    'Sum of all debit lines. Must equal total_credit (enforced by ck_jeh_balanced).';
COMMENT ON COLUMN journal_entry_headers.total_credit IS
    'Sum of all credit lines. Must equal total_debit (enforced by ck_jeh_balanced).';
COMMENT ON COLUMN journal_entry_headers.source_draft_id IS
    'Soft link to journal_drafts.id. No hard FK — decoupled for independent evolution.';
COMMENT ON COLUMN journal_entry_headers.posting_log_id IS
    'Soft link to posting_logs. Set when ERP connector execution occurred.';
COMMENT ON COLUMN journal_entry_headers.evidence_bundle_id IS
    'Soft link to evidence_bundles. Nullable — set when evidence bundle was created.';
COMMENT ON COLUMN journal_entry_headers.reversed_by_entry_id IS
    'Points to the reversing entry if this entry was reversed. Append-only reversal model.';
COMMENT ON COLUMN journal_entry_headers.correction_of_entry_id IS
    'Points to the original entry if this is a correction. Append-only correction model.';
COMMENT ON COLUMN journal_entry_headers.metadata_json IS
    'Non-financial metadata: connector response summary, etc. No api_key or secrets.';


-- =============================================================================
-- B) journal_entry_lines — immutable double-entry lines per header
-- =============================================================================

CREATE TABLE IF NOT EXISTS journal_entry_lines (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               TEXT            NOT NULL,

    -- Parent header reference
    journal_entry_id        UUID            NOT NULL
                                REFERENCES journal_entry_headers(id)
                                ON DELETE CASCADE,

    -- Line ordering
    line_no                 INTEGER         NOT NULL,

    -- Chart of accounts
    account_code            TEXT            NOT NULL,
    account_name            TEXT            NULL,

    -- Double-entry amounts
    debit                   NUMERIC(18,2)   NOT NULL DEFAULT 0,
    credit                  NUMERIC(18,2)   NOT NULL DEFAULT 0,

    -- Currency
    currency                TEXT            NOT NULL DEFAULT 'GEL',
    exchange_rate           NUMERIC(18,8)   NOT NULL DEFAULT 1,

    -- Functional currency amount (GEL)
    amount_gel              NUMERIC(18,2)   NOT NULL DEFAULT 0,

    -- Optional cross-references (soft links)
    counterparty_id         UUID            NULL,
    document_id             UUID            NULL,
    bank_transaction_id     UUID            NULL,

    -- Account classification (used by financial_statements_service posted-ledger queries)
    account_type            TEXT            NULL,
    cashflow_category       TEXT            NULL,

    -- Tax metadata
    tax_code                TEXT            NULL,
    vat_amount              NUMERIC(18,2)   NULL,

    -- Description and integrity
    description             TEXT            NULL,
    line_hash               TEXT            NULL,

    -- Audit timestamp
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- -------------------------------------------------------------------------
    -- Constraints
    -- -------------------------------------------------------------------------

    -- Tenant must be present
    CONSTRAINT ck_jel_tenant_nonempty
        CHECK (tenant_id <> ''),

    -- Account code must be present
    CONSTRAINT ck_jel_account_nonempty
        CHECK (account_code <> ''),

    -- Debit must be non-negative
    CONSTRAINT ck_jel_debit_nonneg
        CHECK (debit >= 0),

    -- Credit must be non-negative
    CONSTRAINT ck_jel_credit_nonneg
        CHECK (credit >= 0),

    -- At least one of debit or credit must be non-zero per line.
    -- A line that is both zero is meaningless.
    CONSTRAINT ck_jel_nonzero
        CHECK (debit > 0 OR credit > 0),

    -- A single line must not have both debit AND credit positive simultaneously.
    -- Standard double-entry: each line is either a debit or a credit, not both.
    CONSTRAINT ck_jel_not_both_positive
        CHECK (NOT (debit > 0 AND credit > 0)),

    -- Unique line ordering within each journal entry
    CONSTRAINT uq_jel_line_no
        UNIQUE (journal_entry_id, line_no)
);

COMMENT ON TABLE journal_entry_lines IS
    'Immutable double-entry lines for each posted journal entry header. '
    'Lines are append-only — reversals and corrections create new lines in new headers. '
    'tenant_id must match the parent header tenant_id (enforced at application layer). '
    'This migration is additive only. It does NOT change report runtime behavior. '
    'This migration is NOT executed by Task 11C-H4.';

COMMENT ON COLUMN journal_entry_lines.journal_entry_id IS
    'FK to journal_entry_headers(id). Cascade-deletes with parent header.';
COMMENT ON COLUMN journal_entry_lines.line_hash IS
    'SHA-256 of (journal_entry_id, line_no, account_code, debit, credit, amount_gel). '
    'Integrity check — detect any tampering with immutable line fields.';
COMMENT ON COLUMN journal_entry_lines.debit IS
    'Debit amount in line currency. Must be >= 0. Cannot be positive if credit > 0.';
COMMENT ON COLUMN journal_entry_lines.credit IS
    'Credit amount in line currency. Must be >= 0. Cannot be positive if debit > 0.';


-- =============================================================================
-- C) journal_entry_sources — source/evidence linkage per header
-- =============================================================================

CREATE TABLE IF NOT EXISTS journal_entry_sources (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               TEXT            NOT NULL,

    -- Parent header reference
    journal_entry_id        UUID            NOT NULL
                                REFERENCES journal_entry_headers(id)
                                ON DELETE CASCADE,

    -- Source object type and identifier (soft link)
    source_type             TEXT            NOT NULL,
    source_id               TEXT            NOT NULL,

    -- Audit timestamp
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_jes_tenant_nonempty
        CHECK (tenant_id <> ''),

    CONSTRAINT ck_jes_source_type_nonempty
        CHECK (source_type <> ''),

    CONSTRAINT ck_jes_source_id_nonempty
        CHECK (source_id <> '')
);

COMMENT ON TABLE journal_entry_sources IS
    'Source/evidence linkage for each posted journal entry. '
    'Links a posted header to its originating objects: draft, document, bank transaction, etc. '
    'Soft links (TEXT source_id) to decouple from FK types. '
    'This migration is additive only. NOT executed by Task 11C-H4.';


-- =============================================================================
-- D) Indexes — all with IF NOT EXISTS for idempotency
-- =============================================================================

-- journal_entry_headers indexes

CREATE INDEX IF NOT EXISTS idx_jeh_tenant
    ON journal_entry_headers (tenant_id);

CREATE INDEX IF NOT EXISTS idx_jeh_tenant_period
    ON journal_entry_headers (tenant_id, period);

CREATE INDEX IF NOT EXISTS idx_jeh_tenant_entry_date
    ON journal_entry_headers (tenant_id, entry_date);

CREATE INDEX IF NOT EXISTS idx_jeh_tenant_status
    ON journal_entry_headers (tenant_id, status)
    WHERE status = 'posted';

CREATE INDEX IF NOT EXISTS idx_jeh_tenant_source_draft
    ON journal_entry_headers (tenant_id, source_draft_id)
    WHERE source_draft_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_jeh_tenant_posting_log
    ON journal_entry_headers (tenant_id, posting_log_id)
    WHERE posting_log_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_jeh_tenant_evidence_bundle
    ON journal_entry_headers (tenant_id, evidence_bundle_id)
    WHERE evidence_bundle_id IS NOT NULL;

-- journal_entry_lines indexes

CREATE INDEX IF NOT EXISTS idx_jel_tenant
    ON journal_entry_lines (tenant_id);

CREATE INDEX IF NOT EXISTS idx_jel_tenant_journal_entry
    ON journal_entry_lines (tenant_id, journal_entry_id);

CREATE INDEX IF NOT EXISTS idx_jel_tenant_account_code
    ON journal_entry_lines (tenant_id, account_code);

CREATE INDEX IF NOT EXISTS idx_jel_tenant_counterparty
    ON journal_entry_lines (tenant_id, counterparty_id)
    WHERE counterparty_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_jel_tenant_document
    ON journal_entry_lines (tenant_id, document_id)
    WHERE document_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_jel_tenant_bank_transaction
    ON journal_entry_lines (tenant_id, bank_transaction_id)
    WHERE bank_transaction_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_jel_tenant_account_type
    ON journal_entry_lines (tenant_id, account_type)
    WHERE account_type IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_jel_tenant_cashflow_category
    ON journal_entry_lines (tenant_id, cashflow_category)
    WHERE cashflow_category IS NOT NULL;

-- journal_entry_sources indexes

CREATE INDEX IF NOT EXISTS idx_jes_tenant_journal_entry
    ON journal_entry_sources (tenant_id, journal_entry_id);


-- =============================================================================
-- E) End — schema-only migration
--
--   This migration only prepares schema.
--   Runtime service implementation: Task 11C-H5 (posting service write)
--   Report migration: Task 11C-H6
--   Reversal/correction/audit export: Task 11C-H7
--   Optional backfill: Task 11C-H8 (separate approval required)
--
--   Approval/posting/connector business logic: unchanged.
--   Balance.ge remains inactive. All activation gates remain NOT MET.
--   journal_drafts JSONB remains untouched.
--   No data is backfilled. No existing columns are removed or altered.
--   THIS MIGRATION IS NOT EXECUTED BY TASK 11C-H4.
-- =============================================================================
