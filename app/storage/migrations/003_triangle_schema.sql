-- Migration 003: Triangle Reconciliation Schema
-- waybills + tax_invoices + commercial_invoices + triangle_matches + document_corrections

-- ── Waybills (ზედნადები) ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS waybills (
    id                  SERIAL PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    waybill_number      TEXT NOT NULL,
    waybill_date        DATE,
    seller_inn          TEXT,
    seller_name         TEXT,
    buyer_inn           TEXT,
    buyer_name          TEXT,
    transport_from      TEXT,
    transport_to        TEXT,
    vehicle_number      TEXT,
    driver_name         TEXT,
    line_items          JSONB DEFAULT '[]',
    subtotal            DECIMAL(15,2),
    vat_amount          DECIMAL(15,2),
    total_amount        DECIMAL(15,2),
    status              TEXT DEFAULT 'imported' CHECK (status IN ('imported','matched','corrected','cancelled')),
    notes               TEXT,
    -- correction tracking
    version             INTEGER DEFAULT 1,
    original_waybill_id INTEGER REFERENCES waybills(id) ON DELETE SET NULL,
    -- source document
    source_document_id  INTEGER,
    raw_text            TEXT,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_waybills_tenant     ON waybills(tenant_id);
CREATE INDEX IF NOT EXISTS idx_waybills_number     ON waybills(tenant_id, waybill_number);
CREATE INDEX IF NOT EXISTS idx_waybills_seller_inn ON waybills(seller_inn);
CREATE INDEX IF NOT EXISTS idx_waybills_buyer_inn  ON waybills(buyer_inn);
CREATE INDEX IF NOT EXISTS idx_waybills_date       ON waybills(waybill_date);

-- ── Tax Invoices (საგადასახადო ანგარიშ-ფაქტურა) ────────────────────────────
CREATE TABLE IF NOT EXISTS tax_invoices (
    id                      SERIAL PRIMARY KEY,
    tenant_id               TEXT NOT NULL,
    invoice_number          TEXT NOT NULL,
    invoice_series          TEXT,
    invoice_date            DATE,
    seller_inn              TEXT,
    seller_name             TEXT,
    buyer_inn               TEXT,
    buyer_name              TEXT,
    line_items              JSONB DEFAULT '[]',
    subtotal                DECIMAL(15,2),
    vat_amount              DECIMAL(15,2),
    total_amount            DECIMAL(15,2),
    status                  TEXT DEFAULT 'imported' CHECK (status IN ('imported','matched','verified','cancelled')),
    notes                   TEXT,
    -- link to related waybill
    related_waybill_number  TEXT,
    related_waybill_id      INTEGER REFERENCES waybills(id) ON DELETE SET NULL,
    -- source document
    source_document_id      INTEGER,
    raw_text                TEXT,
    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tax_invoices_tenant     ON tax_invoices(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tax_invoices_number     ON tax_invoices(tenant_id, invoice_number);
CREATE INDEX IF NOT EXISTS idx_tax_invoices_seller_inn ON tax_invoices(seller_inn);
CREATE INDEX IF NOT EXISTS idx_tax_invoices_buyer_inn  ON tax_invoices(buyer_inn);
CREATE INDEX IF NOT EXISTS idx_tax_invoices_date       ON tax_invoices(invoice_date);

-- ── Commercial Invoices (ანგარიში / ინვოისი) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS commercial_invoices (
    id                  SERIAL PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    invoice_number      TEXT,
    invoice_date        DATE,
    seller_inn          TEXT,
    seller_name         TEXT,
    buyer_inn           TEXT,
    buyer_name          TEXT,
    line_items          JSONB DEFAULT '[]',
    subtotal            DECIMAL(15,2),
    vat_amount          DECIMAL(15,2),
    total_amount        DECIMAL(15,2),
    currency            TEXT DEFAULT 'GEL',
    status              TEXT DEFAULT 'imported' CHECK (status IN ('imported','matched','paid','cancelled')),
    notes               TEXT,
    -- source document
    source_document_id  INTEGER,
    raw_text            TEXT,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_commercial_inv_tenant     ON commercial_invoices(tenant_id);
CREATE INDEX IF NOT EXISTS idx_commercial_inv_seller_inn ON commercial_invoices(seller_inn);
CREATE INDEX IF NOT EXISTS idx_commercial_inv_buyer_inn  ON commercial_invoices(buyer_inn);
CREATE INDEX IF NOT EXISTS idx_commercial_inv_date       ON commercial_invoices(invoice_date);

-- ── Triangle Matches (3 დოკუმენტის დაბმა) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS triangle_matches (
    id                      SERIAL PRIMARY KEY,
    tenant_id               TEXT NOT NULL,
    -- linked documents (all optional — partial matches allowed)
    waybill_id              INTEGER REFERENCES waybills(id) ON DELETE SET NULL,
    tax_invoice_id          INTEGER REFERENCES tax_invoices(id) ON DELETE SET NULL,
    commercial_invoice_id   INTEGER REFERENCES commercial_invoices(id) ON DELETE SET NULL,
    -- match quality
    match_score             DECIMAL(5,4) DEFAULT 0,
    match_status            TEXT DEFAULT 'partial' CHECK (match_status IN ('full','partial','mismatch')),
    mismatch_fields         JSONB DEFAULT '[]',
    -- totals comparison
    waybill_total           DECIMAL(15,2),
    tax_invoice_total       DECIMAL(15,2),
    commercial_invoice_total DECIMAL(15,2),
    amount_diff             DECIMAL(15,2),
    -- journal draft created from this match
    journal_draft_id        INTEGER,
    matched_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_triangle_tenant      ON triangle_matches(tenant_id);
CREATE INDEX IF NOT EXISTS idx_triangle_waybill     ON triangle_matches(waybill_id);
CREATE INDEX IF NOT EXISTS idx_triangle_tax_invoice ON triangle_matches(tax_invoice_id);
CREATE INDEX IF NOT EXISTS idx_triangle_status      ON triangle_matches(match_status);

-- ── Document Corrections (field-level change log) ───────────────────────────
CREATE TABLE IF NOT EXISTS document_corrections (
    id              SERIAL PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    doc_type        TEXT NOT NULL CHECK (doc_type IN ('waybill','tax_invoice','commercial_invoice')),
    doc_id          INTEGER NOT NULL,
    field_name      TEXT NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    correction_note TEXT,
    corrected_by    TEXT,
    corrected_at    TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_corrections_tenant ON document_corrections(tenant_id);
CREATE INDEX IF NOT EXISTS idx_corrections_doc    ON document_corrections(doc_type, doc_id);

-- ── Row Level Security ───────────────────────────────────────────────────────
ALTER TABLE waybills              ENABLE ROW LEVEL SECURITY;
ALTER TABLE tax_invoices          ENABLE ROW LEVEL SECURITY;
ALTER TABLE commercial_invoices   ENABLE ROW LEVEL SECURITY;
ALTER TABLE triangle_matches      ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_corrections  ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_iso_waybills ON waybills
    USING (COALESCE(current_setting('app.current_tenant_id', true), '') = ''
           OR tenant_id = current_setting('app.current_tenant_id', true));

CREATE POLICY tenant_iso_tax_invoices ON tax_invoices
    USING (COALESCE(current_setting('app.current_tenant_id', true), '') = ''
           OR tenant_id = current_setting('app.current_tenant_id', true));

CREATE POLICY tenant_iso_commercial_invoices ON commercial_invoices
    USING (COALESCE(current_setting('app.current_tenant_id', true), '') = ''
           OR tenant_id = current_setting('app.current_tenant_id', true));

CREATE POLICY tenant_iso_triangle_matches ON triangle_matches
    USING (COALESCE(current_setting('app.current_tenant_id', true), '') = ''
           OR tenant_id = current_setting('app.current_tenant_id', true));

CREATE POLICY tenant_iso_doc_corrections ON document_corrections
    USING (COALESCE(current_setting('app.current_tenant_id', true), '') = ''
           OR tenant_id = current_setting('app.current_tenant_id', true));
