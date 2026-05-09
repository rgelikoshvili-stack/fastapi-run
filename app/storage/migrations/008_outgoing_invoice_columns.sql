-- Bridge Hub Task 10D-F-B
-- Outgoing invoice additive column consolidation.
--
-- This file mirrors existing runtime outgoing invoice column ensures. It is
-- intentionally a column-only migration target and is not executed by tests.

ALTER TABLE outgoing_invoices
    ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS invoice_date DATE,
    ADD COLUMN IF NOT EXISTS delivery_date DATE,
    ADD COLUMN IF NOT EXISTS seller_name TEXT,
    ADD COLUMN IF NOT EXISTS seller_inn TEXT,
    ADD COLUMN IF NOT EXISTS seller_address TEXT,
    ADD COLUMN IF NOT EXISTS seller_phone TEXT,
    ADD COLUMN IF NOT EXISTS seller_bank TEXT,
    ADD COLUMN IF NOT EXISTS seller_swift TEXT,
    ADD COLUMN IF NOT EXISTS seller_account TEXT,
    ADD COLUMN IF NOT EXISTS buyer_address TEXT,
    ADD COLUMN IF NOT EXISTS buyer_phone TEXT,
    ADD COLUMN IF NOT EXISTS due_date DATE,
    ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'GEL',
    ADD COLUMN IF NOT EXISTS exchange_rate NUMERIC(18,6),
    ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMP;
