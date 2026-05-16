# SEC-1: Hardcoded production credentials removed.
# Set DB_HOST and DB_PASSWORD via environment variables.
# This script must only run against a non-production database.
import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

_KNOWN_PRODUCTION_HOSTS = {"35.192.214.120"}

host = os.getenv("DB_HOST")
dbname = os.getenv("DB_NAME", "bridgehub")
user = os.getenv("DB_USER", "postgres")
password = os.getenv("DB_PASSWORD")

if not host:
    print("ERROR: DB_HOST is not set. Use a non-production host only.", file=sys.stderr)
    print("  Example: export DB_HOST=localhost", file=sys.stderr)
    sys.exit(1)
if not password:
    print("ERROR: DB_PASSWORD is not set.", file=sys.stderr)
    sys.exit(1)
if host in _KNOWN_PRODUCTION_HOSTS:
    print(f"ERROR: DB_HOST={host!r} matches a known production IP. Refusing.", file=sys.stderr)
    sys.exit(1)

sql_commands = [
    # --- CREATE TABLES IF NOT EXISTS ---
    """
    CREATE TABLE IF NOT EXISTS tenants (
        id SERIAL PRIMARY KEY,
        name TEXT,
        slug TEXT,
        plan TEXT DEFAULT 'FREE',
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP,
        tenant_id TEXT,
        status TEXT DEFAULT 'active'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS tenant_settings (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT,
        setting_key TEXT,
        setting_value TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS tenant_secrets (
        id SERIAL PRIMARY KEY,
        tenant_id TEXT,
        secret_key TEXT,
        secret_value TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """,

    # --- HARDEN TENANTS TABLE ---
    """
    ALTER TABLE tenants ADD COLUMN IF NOT EXISTS name TEXT;
    """,
    """
    ALTER TABLE tenants ADD COLUMN IF NOT EXISTS slug TEXT;
    """,
    """
    ALTER TABLE tenants ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'FREE';
    """,
    """
    ALTER TABLE tenants ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
    """,
    """
    ALTER TABLE tenants ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW();
    """,
    """
    ALTER TABLE tenants ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
    """,
    """
    ALTER TABLE tenants ADD COLUMN IF NOT EXISTS tenant_id TEXT;
    """,
    """
    ALTER TABLE tenants ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active';
    """,

    # --- HARDEN TENANT_SETTINGS TABLE ---
    """
    ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS tenant_id TEXT;
    """,
    """
    ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS setting_key TEXT;
    """,
    """
    ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS setting_value TEXT;
    """,
    """
    ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW();
    """,
    """
    ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();
    """,

    # --- HARDEN TENANT_SECRETS TABLE ---
    """
    ALTER TABLE tenant_secrets ADD COLUMN IF NOT EXISTS tenant_id TEXT;
    """,
    """
    ALTER TABLE tenant_secrets ADD COLUMN IF NOT EXISTS secret_key TEXT;
    """,
    """
    ALTER TABLE tenant_secrets ADD COLUMN IF NOT EXISTS secret_value TEXT;
    """,
    """
    ALTER TABLE tenant_secrets ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW();
    """,
    """
    ALTER TABLE tenant_secrets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();
    """,

    # --- BACKFILL TENANTS ---
    """
    UPDATE tenants
    SET slug = 'default'
    WHERE slug IS NULL AND (tenant_id = 'default' OR id = 1);
    """,
    """
    UPDATE tenants
    SET tenant_id = COALESCE(tenant_id, slug, 'default')
    WHERE tenant_id IS NULL;
    """,
    """
    UPDATE tenants
    SET name = COALESCE(name, 'Default Tenant')
    WHERE name IS NULL;
    """,
    """
    UPDATE tenants
    SET plan = COALESCE(plan, 'FREE')
    WHERE plan IS NULL;
    """,
    """
    UPDATE tenants
    SET is_active = COALESCE(is_active, TRUE)
    WHERE is_active IS NULL;
    """,
    """
    UPDATE tenants
    SET status = COALESCE(status, 'active')
    WHERE status IS NULL;
    """,

    # --- INSERT DEFAULT TENANT ONLY IF MISSING ---
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM tenants
            WHERE tenant_id = 'default' OR slug = 'default'
        ) THEN
            INSERT INTO tenants (
                name,
                slug,
                plan,
                is_active,
                created_at,
                updated_at,
                tenant_id,
                status
            )
            VALUES (
                'Default Tenant',
                'default',
                'FREE',
                TRUE,
                NOW(),
                NOW(),
                'default',
                'active'
            );
        END IF;
    END $$;
    """,

    # --- INDEXES ---
    """
    CREATE INDEX IF NOT EXISTS idx_tenants_tenant_id
    ON tenants(tenant_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tenants_slug
    ON tenants(slug);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tenant_settings_tenant_id
    ON tenant_settings(tenant_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tenant_secrets_tenant_id
    ON tenant_secrets(tenant_id);
    """
]

conn = psycopg2.connect(
    host=host,
    dbname=dbname,
    user=user,
    password=password,
)
conn.autocommit = True

try:
    with conn.cursor() as cur:
        for i, sql in enumerate(sql_commands, start=1):
            print(f"Running SQL #{i}...")
            cur.execute(sql)
    print("Tenant tables migration completed successfully.")
finally:
    conn.close()