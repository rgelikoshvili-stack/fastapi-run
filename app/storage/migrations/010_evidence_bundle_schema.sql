-- =============================================================================
-- Bridge Hub — Migration 010
-- Task 11C-G1: Evidence Bundle Additive Schema Migration
--
-- PURPOSE:
--   Additive schema for the Evidence Bundle foundation. Evidence bundles
--   attach verifiable audit metadata — source documents, OCR results,
--   AI reasoning, approval events, posting log references — to every
--   approval and posting operation without changing business logic.
--
-- REVIEW STATUS:
--   Review-only in Task 11C-G1. Created but NOT executed.
--
-- EXECUTION:
--   Do not execute manually against production.
--   Future execution must be through the approved migration process only.
--   All statements use IF NOT EXISTS guards and are idempotent.
--
-- SCOPE:
--   A) CREATE TABLE IF NOT EXISTS evidence_bundles
--   B) CREATE TABLE IF NOT EXISTS evidence_bundle_events
--   C) CREATE INDEX IF NOT EXISTS (all evidence bundle indexes)
--
-- SAFETY RULES:
--   - Additive only. Does not remove, modify, or destroy existing data.
--   - Does not change approval/posting/connector business logic.
--   - Does not activate Balance.ge.
--   - Does not introduce credential, api_key, password, or secret fields.
--   - Does not backfill data.
--   - Payload preview is stored as a HASH only — never raw connector payload.
--   - AI reasoning is JSONB metadata — never raw API keys or secrets.
--
-- CROSS-REFERENCES:
--   docs/trust-foundation-runtime-implementation-sequence.md
--   docs/balance-ge-activation-final-checklist.md
-- =============================================================================


-- =============================================================================
-- A) Evidence bundles — primary audit metadata table
-- =============================================================================

CREATE TABLE IF NOT EXISTS evidence_bundles (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               TEXT        NOT NULL,

    -- Source identification
    source_type             TEXT        NOT NULL,
    source_id               TEXT,
    source_file_id          TEXT,
    source_file_hash        TEXT,

    -- Cross-reference identifiers (all TEXT to decouple from FK types)
    bank_transaction_id     TEXT,
    document_id             TEXT,
    ocr_result_id           TEXT,
    journal_draft_id        TEXT,
    journal_entry_id        TEXT,
    approval_event_id       TEXT,
    posting_log_id          TEXT,

    -- Connector metadata (no raw credentials, no raw payload)
    connector_provider      TEXT,
    connector_operation     TEXT,
    payload_preview_hash    TEXT,

    -- AI and extraction metadata (JSONB, no raw secrets)
    ai_reasoning            JSONB       NOT NULL DEFAULT '{}'::jsonb,
    extracted_fields        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    risk_flags              JSONB       NOT NULL DEFAULT '[]'::jsonb,
    confidence              NUMERIC,

    -- Lifecycle
    status                  TEXT        NOT NULL DEFAULT 'draft',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by              TEXT,
    updated_by              TEXT,

    CONSTRAINT ck_evidence_bundles_source_type_nonempty
        CHECK (source_type <> ''),

    CONSTRAINT ck_evidence_bundles_status
        CHECK (status IN ('draft', 'ready', 'approved', 'posted', 'failed', 'archived')),

    CONSTRAINT ck_evidence_bundles_confidence_range
        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

COMMENT ON TABLE evidence_bundles IS
    'Verifiable audit metadata for approval and posting operations. '
    'Payload preview is stored as a hash only — never raw connector payload. '
    'Runtime implementation: Task 11C-G2/G3/G4. '
    'Balance.ge remains inactive.';

COMMENT ON COLUMN evidence_bundles.source_type IS
    'Origin category: bank_transaction, document, ocr, manual, api, etc.';
COMMENT ON COLUMN evidence_bundles.source_file_hash IS
    'SHA-256 hex digest of the source file. Never stores file content.';
COMMENT ON COLUMN evidence_bundles.payload_preview_hash IS
    'SHA-256 hex digest of the connector payload preview. Never stores raw payload.';
COMMENT ON COLUMN evidence_bundles.ai_reasoning IS
    'AI classification metadata: model, reasoning, classification. No api_key/secret.';
COMMENT ON COLUMN evidence_bundles.extracted_fields IS
    'OCR/extraction output fields. No api_key, password, or credential values.';
COMMENT ON COLUMN evidence_bundles.risk_flags IS
    'List of risk flag strings (e.g. ["HIGH_AMOUNT", "UNRECOGNIZED_PARTNER"]).';
COMMENT ON COLUMN evidence_bundles.confidence IS
    'AI/model confidence score, 0.0–1.0. NULL if not applicable.';


-- =============================================================================
-- B) Evidence bundle events — immutable audit event log per bundle
-- =============================================================================

CREATE TABLE IF NOT EXISTS evidence_bundle_events (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               TEXT        NOT NULL,
    evidence_bundle_id      UUID        NOT NULL
                                REFERENCES evidence_bundles(id)
                                ON DELETE CASCADE,
    event_type              TEXT        NOT NULL,
    actor                   TEXT,
    event_ref_type          TEXT,
    event_ref_id            TEXT,
    metadata                JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_evidence_bundle_events_type_nonempty
        CHECK (event_type <> '')
);

COMMENT ON TABLE evidence_bundle_events IS
    'Immutable event log for evidence bundle lifecycle transitions. '
    'Raw credential values must never appear in any row. '
    'metadata must not contain api_key, password, token, or secret.';

COMMENT ON COLUMN evidence_bundle_events.evidence_bundle_id IS
    'References evidence_bundles(id). Cascade-deletes with parent bundle.';
COMMENT ON COLUMN evidence_bundle_events.event_type IS
    'Event kind: created, ai_attached, fields_attached, approval_linked, '
    'posting_linked, entry_linked, status_changed, archived.';


-- =============================================================================
-- C) Indexes
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_evidence_bundles_tenant
    ON evidence_bundles (tenant_id);

CREATE INDEX IF NOT EXISTS idx_evidence_bundles_source
    ON evidence_bundles (tenant_id, source_type, source_id);

CREATE INDEX IF NOT EXISTS idx_evidence_bundles_journal_draft
    ON evidence_bundles (tenant_id, journal_draft_id)
    WHERE journal_draft_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_evidence_bundles_journal_entry
    ON evidence_bundles (tenant_id, journal_entry_id)
    WHERE journal_entry_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_evidence_bundles_approval
    ON evidence_bundles (tenant_id, approval_event_id)
    WHERE approval_event_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_evidence_bundles_posting_log
    ON evidence_bundles (tenant_id, posting_log_id)
    WHERE posting_log_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_evidence_bundle_events_bundle
    ON evidence_bundle_events (evidence_bundle_id);

CREATE INDEX IF NOT EXISTS idx_evidence_bundle_events_tenant_created
    ON evidence_bundle_events (tenant_id, created_at);


-- =============================================================================
-- D) End — schema-only migration
--
--   This migration only prepares schema.
--   Runtime service implementation: Task 11C-G2/G3/G4.
--   Approval/posting/connector business logic: unchanged.
--   Balance.ge remains inactive. All activation gates remain NOT MET.
--   No data is backfilled. No existing columns are removed or altered.
-- =============================================================================
