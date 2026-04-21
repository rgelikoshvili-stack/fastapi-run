-- Migration 002: Row Level Security (defense-in-depth on top of WHERE tenant_id)
-- Safe policy: if app.current_tenant_id not set → pass through (old code unaffected)
--              if set → must match tenant_id (new code enforced)

-- ── Enable RLS on new tables (zero risk — no existing queries) ──────────────
ALTER TABLE counterparties ENABLE ROW LEVEL SECURITY;
ALTER TABLE processed_documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_iso_counterparties ON counterparties
    USING (
        COALESCE(current_setting('app.current_tenant_id', true), '') = ''
        OR tenant_id = current_setting('app.current_tenant_id', true)
    );

CREATE POLICY tenant_iso_processed_docs ON processed_documents
    USING (
        COALESCE(current_setting('app.current_tenant_id', true), '') = ''
        OR tenant_id = current_setting('app.current_tenant_id', true)
    );

-- ── Enable RLS on journal_drafts (safe fallback for existing code) ───────────
ALTER TABLE journal_drafts ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_iso_drafts ON journal_drafts
    USING (
        COALESCE(current_setting('app.current_tenant_id', true), '') = ''
        OR tenant_id = current_setting('app.current_tenant_id', true)
    );

-- ── Superuser bypass (allows migrations and admin scripts to work) ───────────
ALTER TABLE journal_drafts FORCE ROW LEVEL SECURITY;
ALTER TABLE counterparties FORCE ROW LEVEL SECURITY;
ALTER TABLE processed_documents FORCE ROW LEVEL SECURITY;
