-- Migration 004: Outgoing Invoices
-- outgoing_invoices + invoice_counters
-- + adds notes column to waybills and tax_invoices (if not present)

-- ── Outgoing Invoices ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outgoing_invoices (
    id                      SERIAL PRIMARY KEY,
    tenant_id               TEXT NOT NULL,
    invoice_number          TEXT,
    invoice_type            TEXT CHECK (invoice_type IN ('goods', 'service')),
    status                  TEXT DEFAULT 'draft' CHECK (status IN ('draft','finalized','cancelled')),
    buyer_inn               TEXT,
    buyer_name              TEXT,
    buyer_email             TEXT,
    -- transport (goods only)
    transport_from          TEXT,
    transport_to            TEXT,
    vehicle_number          TEXT,
    driver_name             TEXT,
    -- financials
    line_items              JSONB DEFAULT '[]',
    subtotal                DECIMAL(15,2) DEFAULT 0,
    vat_amount              DECIMAL(15,2) DEFAULT 0,
    total_amount            DECIMAL(15,2) DEFAULT 0,
    -- ← comment propagates to waybill.notes + tax_invoice.notes
    comment                 TEXT,
    -- generated linked documents
    generated_waybill_id    INTEGER REFERENCES waybills(id) ON DELETE SET NULL,
    generated_tax_invoice_id INTEGER REFERENCES tax_invoices(id) ON DELETE SET NULL,
    -- audit
    created_by              INTEGER,
    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW(),
    finalized_at            TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_outgoing_tenant    ON outgoing_invoices(tenant_id);
CREATE INDEX IF NOT EXISTS idx_outgoing_status    ON outgoing_invoices(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_outgoing_buyer_inn ON outgoing_invoices(buyer_inn);
CREATE INDEX IF NOT EXISTS idx_outgoing_created   ON outgoing_invoices(created_at);

-- ── Invoice Counters (per-tenant per-year numbering) ─────────────────────────
CREATE TABLE IF NOT EXISTS invoice_counters (
    tenant_id   TEXT NOT NULL,
    year        INTEGER NOT NULL,
    counter     INTEGER DEFAULT 0,
    PRIMARY KEY (tenant_id, year)
);

-- ── Add notes column to waybills + tax_invoices (safe if already exists) ────
ALTER TABLE waybills     ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE tax_invoices ADD COLUMN IF NOT EXISTS notes TEXT;

-- ── Row Level Security ───────────────────────────────────────────────────────
ALTER TABLE outgoing_invoices ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_iso_outgoing ON outgoing_invoices
    USING (
        COALESCE(current_setting('app.current_tenant_id', true), '') = ''
        OR tenant_id = current_setting('app.current_tenant_id', true)
    );
