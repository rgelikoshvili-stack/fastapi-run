-- Bridge Hub SaaS Transformation — Migration 001
-- Extends tenants table, adds counterparties, processed_documents, document intelligence fields

-- ── Extend tenants table ────────────────────────────────────────────────────
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS company_inn TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS company_name_legal TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS company_name_aliases JSONB DEFAULT '[]';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS company_type TEXT DEFAULT 'legal_entity';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS is_vat_payer BOOLEAN DEFAULT TRUE;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS owner_personal_id TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS subscription_tier TEXT DEFAULT 'trial';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS default_bank TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS default_erp TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS fiscal_year_start TEXT DEFAULT '01-01';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'GEL';

CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_company_inn
    ON tenants(company_inn) WHERE company_inn IS NOT NULL;

-- Fix existing ALTE University tenant
UPDATE tenants
SET
    company_inn = '202192643',
    company_name_legal = 'შავი ზღვის უნივერსიტეტი',
    company_name_aliases = '["ამ­ტე", "ALTE", "Alte University", "შავი ზღვის უნივერსიტეტი"]'::jsonb,
    company_type = 'legal_entity',
    is_vat_payer = TRUE,
    owner_personal_id = '01017036107',
    subscription_tier = 'business',
    trial_ends_at = NOW() + INTERVAL '365 days'
WHERE tenant_id = '01017036108';

-- ── Counterparties (vendors/customers) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS counterparties (
    id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    inn TEXT NOT NULL,
    name TEXT NOT NULL,
    name_aliases JSONB DEFAULT '[]',
    type TEXT DEFAULT 'vendor',
    category TEXT,
    default_debit_account TEXT,
    default_credit_account TEXT,
    is_vat_payer BOOLEAN DEFAULT TRUE,
    is_non_resident BOOLEAN DEFAULT FALSE,
    country_code TEXT DEFAULT 'GE',
    total_transactions INTEGER DEFAULT 0,
    total_amount_bought DECIMAL(15,2) DEFAULT 0,
    total_amount_sold DECIMAL(15,2) DEFAULT 0,
    last_transaction_at TIMESTAMP,
    first_seen_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_tenant_inn_counterparty UNIQUE (tenant_id, inn)
);

CREATE INDEX IF NOT EXISTS idx_counterparties_tenant ON counterparties(tenant_id, inn);

-- ── Processed documents (dedup + extraction cache) ──────────────────────────
CREATE TABLE IF NOT EXISTS processed_documents (
    id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_name TEXT,
    file_size_bytes INTEGER,
    mime_type TEXT,
    extraction_method TEXT,
    raw_text TEXT,
    extracted_data JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_tenant_file_hash UNIQUE (tenant_id, file_hash)
);

CREATE INDEX IF NOT EXISTS idx_processed_docs_tenant_hash
    ON processed_documents(tenant_id, file_hash);

-- ── Extend journal_drafts with document intelligence fields ─────────────────
ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS our_role TEXT;
ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS operation_type TEXT;
ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS operation_category TEXT;
ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS counterparty_inn TEXT;
ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS counterparty_name TEXT;
ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS document_series TEXT;
ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS document_number TEXT;
ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS is_foreign_doc BOOLEAN DEFAULT FALSE;
ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS journal_entries JSONB;
ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS raw_extraction JSONB;
ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS source_document_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_drafts_doc_series_number
    ON journal_drafts(tenant_id, document_series, document_number)
    WHERE document_series IS NOT NULL;
