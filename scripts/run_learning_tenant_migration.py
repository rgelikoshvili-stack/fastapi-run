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
    # learning_feedback
    "ALTER TABLE learning_feedback ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default';",
    "UPDATE learning_feedback SET tenant_id = 'default' WHERE tenant_id IS NULL;",
    "CREATE INDEX IF NOT EXISTS idx_learning_feedback_tenant_id ON learning_feedback(tenant_id);",

    # learning_patterns
    "ALTER TABLE learning_patterns ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default';",
    "UPDATE learning_patterns SET tenant_id = 'default' WHERE tenant_id IS NULL;",
    "CREATE INDEX IF NOT EXISTS idx_learning_patterns_tenant_id ON learning_patterns(tenant_id);",

    # transaction_memory
    "ALTER TABLE transaction_memory ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default';",
    "UPDATE transaction_memory SET tenant_id = 'default' WHERE tenant_id IS NULL;",
    "CREATE INDEX IF NOT EXISTS idx_transaction_memory_tenant_id ON transaction_memory(tenant_id);",

    # erp_posting_memory
    "ALTER TABLE erp_posting_memory ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default';",
    "UPDATE erp_posting_memory SET tenant_id = 'default' WHERE tenant_id IS NULL;",
    "CREATE INDEX IF NOT EXISTS idx_erp_posting_memory_tenant_id ON erp_posting_memory(tenant_id);",

    # async_queue
    "ALTER TABLE async_queue ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default';",
    "UPDATE async_queue SET tenant_id = 'default' WHERE tenant_id IS NULL;",
    "CREATE INDEX IF NOT EXISTS idx_async_queue_tenant_id ON async_queue(tenant_id);",
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
    print("Learning tenant migration completed successfully.")
finally:
    conn.close()