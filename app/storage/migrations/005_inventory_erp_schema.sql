-- Bridge Hub Task 10D-B
-- Inventory ERP schema canonical additive migration.
--
-- This migration mirrors the existing runtime inventory bootstrap in
-- app/api/services/inventory_service.py. It is intentionally additive only and
-- does not remove the runtime compatibility wrapper.

CREATE TABLE IF NOT EXISTS inventory_categories (
    id          SERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    parent_id   INTEGER REFERENCES inventory_categories(id),
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, code)
);

CREATE TABLE IF NOT EXISTS warehouses (
    id              SERIAL PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    address         TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    is_default      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, code)
);

CREATE TABLE IF NOT EXISTS inventory_items (
    id              SERIAL PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    item_code       TEXT NOT NULL,
    item_name       TEXT NOT NULL,
    description     TEXT,
    category_id     INTEGER REFERENCES inventory_categories(id),
    purchase_price  NUMERIC(15,2) DEFAULT 0,
    selling_price   NUMERIC(15,2) DEFAULT 0,
    unit_of_measure TEXT NOT NULL DEFAULT 'piece',
    reorder_level   INTEGER DEFAULT 0,
    costing_method  TEXT DEFAULT 'fifo' CHECK (costing_method IN ('fifo','lifo','average')),
    default_warehouse_id INTEGER REFERENCES warehouses(id),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, item_code)
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id              SERIAL PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    item_id         INTEGER NOT NULL REFERENCES inventory_items(id),
    movement_type   TEXT NOT NULL CHECK (movement_type IN ('in','out','transfer','adjustment')),
    quantity        NUMERIC(15,3) NOT NULL,
    unit_cost       NUMERIC(15,4) NOT NULL DEFAULT 0,
    warehouse_from  INTEGER REFERENCES warehouses(id),
    warehouse_to    INTEGER REFERENCES warehouses(id),
    reference_type  TEXT,
    reference_doc   TEXT,
    movement_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id              SERIAL PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    po_number       TEXT NOT NULL,
    supplier_name   TEXT,
    supplier_inn    TEXT,
    po_date         DATE NOT NULL DEFAULT CURRENT_DATE,
    expected_date   DATE,
    received_date   DATE,
    status          TEXT DEFAULT 'draft' CHECK (status IN ('draft','sent','partial','received','cancelled')),
    subtotal        NUMERIC(15,2) DEFAULT 0,
    vat_amount      NUMERIC(15,2) DEFAULT 0,
    total_amount    NUMERIC(15,2) DEFAULT 0,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, po_number)
);

CREATE TABLE IF NOT EXISTS purchase_order_lines (
    id              SERIAL PRIMARY KEY,
    po_id           INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    item_id         INTEGER NOT NULL REFERENCES inventory_items(id),
    quantity_ordered NUMERIC(15,3) NOT NULL,
    quantity_received NUMERIC(15,3) DEFAULT 0,
    unit_price      NUMERIC(15,4) NOT NULL,
    line_number     INTEGER,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_inventory_items_tenant
    ON inventory_items(tenant_id, is_active);

CREATE INDEX IF NOT EXISTS idx_stock_movements_tenant_item
    ON stock_movements(tenant_id, item_id, movement_date DESC);

CREATE INDEX IF NOT EXISTS idx_purchase_orders_tenant_status
    ON purchase_orders(tenant_id, status);
