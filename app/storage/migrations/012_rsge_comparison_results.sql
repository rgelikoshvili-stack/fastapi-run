-- Migration 012: RS.ge document comparison results
-- Run ONLY after approval. Non-destructive (CREATE IF NOT EXISTS).
-- Do NOT execute on production without explicit approval.

CREATE TABLE IF NOT EXISTS rsge_comparison_results (
    id                      SERIAL PRIMARY KEY,
    tenant_id               TEXT          NOT NULL,
    rsge_document_id        INTEGER,
    rsge_waybill_id         INTEGER,
    compare_target_type     TEXT          NOT NULL DEFAULT 'evidence',
    compare_target_id       INTEGER,
    comparison_status       TEXT          NOT NULL DEFAULT 'requires_review',
    seller_buyer_status     TEXT          DEFAULT 'matched',
    amount_status           TEXT          DEFAULT 'matched',
    vat_status              TEXT          DEFAULT 'matched',
    line_status             TEXT          DEFAULT 'matched',
    product_mapping_status  TEXT          DEFAULT 'matched',
    date_status             TEXT          DEFAULT 'matched',
    rsge_status             TEXT,
    bridge_status           TEXT,
    amount_diff             NUMERIC(18,4) DEFAULT 0,
    vat_diff                NUMERIC(18,4) DEFAULT 0,
    wb_amount               NUMERIC(18,4) DEFAULT 0,
    inv_amount              NUMERIC(18,4) DEFAULT 0,
    line_diff_count         INTEGER       DEFAULT 0,
    mismatch_summary        TEXT,
    diff_lines              JSONB         DEFAULT '[]',
    risk_level              TEXT          DEFAULT 'low',
    notes                   TEXT,
    reviewed_by             TEXT,
    reviewed_at             TIMESTAMPTZ,
    created_by              TEXT,
    created_at              TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_rsge_comparison_tenant
    ON rsge_comparison_results (tenant_id);

CREATE INDEX IF NOT EXISTS idx_rsge_comparison_document
    ON rsge_comparison_results (tenant_id, rsge_document_id);

CREATE INDEX IF NOT EXISTS idx_rsge_comparison_waybill
    ON rsge_comparison_results (tenant_id, rsge_waybill_id);

CREATE INDEX IF NOT EXISTS idx_rsge_comparison_status
    ON rsge_comparison_results (tenant_id, comparison_status);

-- Aliases in existing simplified table (backward compat)
ALTER TABLE rsge_comparison_results
    ADD COLUMN IF NOT EXISTS waybill_id  INTEGER,
    ADD COLUMN IF NOT EXISTS document_id INTEGER;
