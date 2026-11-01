-- Chat166: Add a monotonic user session version for access/refresh revocation.
-- Apply ONLY to an approved isolated staging database, never at app startup.
-- Production DDL requires separate backup/restore evidence and written approval.
-- PostgreSQL 15+: constant DEFAULT 1 is additive; existing sessions are NOT
-- revoked until JWT_SESSION_VERSION_ENABLED=1 is explicitly activated.
DO $$
BEGIN
    IF to_regclass('users') IS NULL THEN
        RAISE EXCEPTION 'Chat166 expected users table missing';
    END IF;
END
$$;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS auth_version BIGINT NOT NULL DEFAULT 1;

-- PostgreSQL 15 has no ADD CONSTRAINT IF NOT EXISTS.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'users'::regclass
          AND conname = 'users_auth_version_positive'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_auth_version_positive CHECK (auth_version >= 1);
    END IF;
END
$$;

-- Production rollout: migrate first, verify schema/roles/backups, deploy code
-- with flag OFF, coordinate all replicas, then explicitly enable flag.
-- Activation intentionally invalidates pre-migration JWTs lacking auth_version.
