-- Chat161. Provision ONLY in isolated staging first; NOT applied automatically.
-- Durable one-time OAuth state for multi-replica Cloud Run callback processing.
CREATE TABLE IF NOT EXISTS oauth_login_states (
    state_hash CHAR(64) PRIMARY KEY CHECK (state_hash ~ '^[0-9a-f]{64}$'),
    tenant_id TEXT NOT NULL CHECK (
        tenant_id = btrim(tenant_id)
        AND tenant_id <> ''
        AND lower(tenant_id) <> 'default'
    ),
    provider TEXT NOT NULL CHECK (provider IN ('google', 'microsoft')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_oauth_login_states_expires_at
    ON oauth_login_states (expires_at);
-- Rows expire after ten minutes; schedule a bounded cleanup job:
-- DELETE FROM oauth_login_states WHERE expires_at < NOW();
-- This table contains no raw state codes, user passwords, or provider tokens.
-- Production DDL must be separately approved and deployed before enabling this branch.
