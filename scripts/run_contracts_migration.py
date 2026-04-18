"""
Migration: add tenant_id column to contracts and contract_milestones.
Existing rows default to 'default' tenant.
"""
import os
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("""
    ALTER TABLE contracts
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default'
""")

cur.execute("""
    ALTER TABLE contract_milestones
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default'
""")

cur.execute("""
    UPDATE contracts SET tenant_id = 'default' WHERE tenant_id IS NULL
""")

cur.execute("""
    UPDATE contract_milestones SET tenant_id = 'default' WHERE tenant_id IS NULL
""")

cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_contracts_tenant_id ON contracts(tenant_id)
""")

conn.commit()
cur.close()
conn.close()
print("contracts migration complete")
