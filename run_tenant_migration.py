import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

host = os.getenv("DB_HOST", "35.192.214.120")
dbname = os.getenv("DB_NAME", "bridgehub")
user = os.getenv("DB_USER", "postgres")
password = os.getenv("DB_PASSWORD", "BridgeHub2026x")

sql_commands = [
    "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default';",
    "ALTER TABLE bank_transactions ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default';",
    "ALTER TABLE learning_patterns ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default';",
    "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default';",
    "ALTER TABLE posting_logs ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default';",
    "ALTER TABLE transaction_memory ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default';",
    "ALTER TABLE erp_posting_memory ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default';",

    "UPDATE journal_drafts SET tenant_id = 'default' WHERE tenant_id IS NULL;",
    "UPDATE bank_transactions SET tenant_id = 'default' WHERE tenant_id IS NULL;",
    "UPDATE learning_patterns SET tenant_id = 'default' WHERE tenant_id IS NULL;",
    "UPDATE audit_events SET tenant_id = 'default' WHERE tenant_id IS NULL;",
    "UPDATE posting_logs SET tenant_id = 'default' WHERE tenant_id IS NULL;",
    "UPDATE transaction_memory SET tenant_id = 'default' WHERE tenant_id IS NULL;",
    "UPDATE erp_posting_memory SET tenant_id = 'default' WHERE tenant_id IS NULL;",

    "CREATE INDEX IF NOT EXISTS idx_journal_drafts_tenant_id ON journal_drafts(tenant_id);",
    "CREATE INDEX IF NOT EXISTS idx_bank_transactions_tenant_id ON bank_transactions(tenant_id);",
    "CREATE INDEX IF NOT EXISTS idx_learning_patterns_tenant_id ON learning_patterns(tenant_id);",
    "CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_id ON audit_events(tenant_id);",
    "CREATE INDEX IF NOT EXISTS idx_posting_logs_tenant_id ON posting_logs(tenant_id);",
    "CREATE INDEX IF NOT EXISTS idx_transaction_memory_tenant_id ON transaction_memory(tenant_id);",
    "CREATE INDEX IF NOT EXISTS idx_erp_posting_memory_tenant_id ON erp_posting_memory(tenant_id);",
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
        for sql in sql_commands:
            print(f"Running: {sql}")
            cur.execute(sql)
    print("Tenant migration completed successfully.")
finally:
    conn.close()