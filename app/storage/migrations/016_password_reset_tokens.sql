-- Chat168: Move legacy password-reset table creation out of the public API.
-- Apply with an authorized migration role in isolated staging FIRST.
-- Never auto-run DDL from /auth/forgot-password or on service startup.
-- Existing tables and outstanding reset links remain preserved.
-- Re-applying this migration is safe (additive, no DROP/DELETE).
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id SERIAL PRIMARY KEY,
    token VARCHAR(128) UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(100) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Privileges for nonowner service roles, if used, must be provisioned through
-- a separately reviewed and least-privilege staging/production role plan.
-- This migration does not grant CREATE or privileged cross-tenant access.
