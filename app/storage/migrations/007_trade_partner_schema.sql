-- Bridge Hub Task 10D-D
-- Trade partner schema canonical additive migration.
--
-- This migration mirrors the existing runtime partner bootstrap in
-- app/startup/migrations.py. It is intentionally additive only and does not
-- remove the runtime compatibility wrapper.

CREATE TABLE IF NOT EXISTS customers (
    id          SERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL DEFAULT 'default',
    name        TEXT NOT NULL,
    email       TEXT,
    phone       TEXT,
    company     TEXT,
    type        TEXT DEFAULT 'client',
    tax_id      TEXT,
    address     TEXT,
    notes       TEXT,
    status      TEXT DEFAULT 'active',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS customer_interactions (
    id          SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
    tenant_id   TEXT NOT NULL DEFAULT 'default',
    type        TEXT,
    note        TEXT,
    amount      NUMERIC,
    created_by  TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_customers_tenant_id
    ON customers(tenant_id);

CREATE INDEX IF NOT EXISTS idx_customers_tenant_type_status
    ON customers(tenant_id, type, status);

CREATE INDEX IF NOT EXISTS idx_customer_interactions_tenant_customer
    ON customer_interactions(tenant_id, customer_id);

CREATE INDEX IF NOT EXISTS idx_customer_interactions_tenant_created_at
    ON customer_interactions(tenant_id, created_at DESC);
