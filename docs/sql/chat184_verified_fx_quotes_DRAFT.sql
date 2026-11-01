-- Chat184 FIN-05: source-attested FX quotes. DRAFT CANDIDATE ONLY.
-- NOT registered at startup and NEVER apply to Production without separate
-- operator approval and source/role/schema migration inventory.
-- The actual NBG publication/effective-date contract and privileged ingestion
-- require independent vendor/sandbox verification (EXTERNAL-HOLD).
-- One public NBG quote store is shared read-only across tenants; no client
-- data, tenant override, manual rates or latest-snapshot fallback.
CREATE TABLE IF NOT EXISTS fx_verified_quotes (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    currency                TEXT NOT NULL CHECK (currency ~ '^[A-Z]{3}$' AND currency <> 'GEL'),
    base_currency           TEXT NOT NULL DEFAULT 'GEL' CHECK (base_currency = 'GEL'),
    source_provider         TEXT NOT NULL CHECK (source_provider = 'NBG'),
    source_revision         TEXT NOT NULL CHECK (btrim(source_revision) <> ''),
    source_payload_sha256   TEXT NOT NULL CHECK (source_payload_sha256 ~ '^[0-9a-f]{64}$'),
    published_date          DATE NOT NULL,
    effective_date          DATE NOT NULL,
    retrieved_at            TIMESTAMPTZ NOT NULL,
    approved_by             TEXT NOT NULL CHECK (btrim(approved_by) <> ''),
    approved_at             TIMESTAMPTZ NOT NULL,
    raw_rate                NUMERIC(18,8) NOT NULL CHECK (raw_rate > 0),
    quantity                NUMERIC(18,0) NOT NULL CHECK (quantity >= 1),
    rate_to_gel             NUMERIC(18,8) NOT NULL CHECK (rate_to_gel > 0),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_fx_source_dates CHECK
        (published_date <= effective_date AND effective_date <= published_date + 7),
    CONSTRAINT ck_fx_rate_quantity CHECK
        (ROUND(raw_rate / quantity, 8) = rate_to_gel),
    CONSTRAINT uq_fx_source_revision UNIQUE(currency, effective_date, source_revision)
);
CREATE INDEX IF NOT EXISTS idx_fx_verified_quotes_asof
    ON fx_verified_quotes (currency, effective_date DESC);
CREATE OR REPLACE FUNCTION fx_verified_quotes_reject_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'FX_VERIFIED_QUOTES_IMMUTABLE';
END $$;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'fx_verified_quotes'::regclass
          AND tgname = 'trg_fx_verified_quotes_immutable'
    ) THEN
        CREATE TRIGGER trg_fx_verified_quotes_immutable
            BEFORE UPDATE OR DELETE ON fx_verified_quotes
            FOR EACH ROW EXECUTE FUNCTION fx_verified_quotes_reject_mutation();
    END IF;
END $$;
REVOKE ALL ON fx_verified_quotes FROM PUBLIC;
-- Only audited privileged importers may INSERT, after independent evidence
-- review. The runtime role receives SELECT ONLY in a separately approved
-- migration. No UPDATE/DELETE permissions or live data backfill.
