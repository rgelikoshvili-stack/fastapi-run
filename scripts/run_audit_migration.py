import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
try:
    cur.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) DEFAULT 'default'")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_id ON audit_events(tenant_id)")
    conn.commit()
    print("OK: audit_events.tenant_id added")
except Exception as e:
    conn.rollback()
    print(f"ERROR: {e}")
cur.close()
conn.close()
print("Done!")
