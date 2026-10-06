-- NEXT-04A4 durable OCR callback replay receipts. Apply only in the approved
-- migration sequence; this is never executed by application startup.
ALTER TABLE processed_documents
    ADD COLUMN ocr_worker_job_id TEXT;

CREATE TABLE ocr_callback_receipts (
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    document_id INTEGER NOT NULL,
    job_type TEXT NOT NULL CHECK (job_type = 'ocr'),
    result_sha256 CHAR(64),
    state TEXT NOT NULL CHECK (state IN ('dispatched', 'processing', 'completed')),
    lease_until TIMESTAMPTZ,
    duplicate_attempts INTEGER NOT NULL DEFAULT 0,
    conflict_attempts INTEGER NOT NULL DEFAULT 0,
    last_duplicate_at TIMESTAMPTZ,
    last_conflict_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, job_id)
);

CREATE INDEX ocr_callback_receipts_document_idx
    ON ocr_callback_receipts (tenant_id, document_id, received_at DESC);

CREATE INDEX processed_documents_ocr_job_idx
    ON processed_documents (tenant_id, ocr_worker_job_id)
    WHERE ocr_worker_job_id IS NOT NULL;

ALTER TABLE ocr_callback_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE ocr_callback_receipts FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_fail_closed_ocr_callback_receipts ON ocr_callback_receipts
    FOR ALL
    USING (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    )
    WITH CHECK (
        NULLIF(btrim(current_setting('app.current_tenant_id', true)), '') IS NOT NULL
        AND tenant_id = btrim(current_setting('app.current_tenant_id', true))
    );
