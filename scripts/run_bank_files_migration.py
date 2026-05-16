# SEC-1: Hardcoded production credentials removed.
# This script previously connected directly to a production IP with a hardcoded password.
# It now requires explicit environment variables and refuses known production hosts.
# Use only against a non-production database.
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

conn = psycopg2.connect(
    host=host,
    dbname=dbname,
    user=user,
    password=password,
)
conn.autocommit = True
cur = conn.cursor()

sqls = [
    "ALTER TABLE processed_bank_files ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) DEFAULT 'default'",
    "UPDATE processed_bank_files SET tenant_id = 'default' WHERE tenant_id IS NULL",
    "ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) DEFAULT 'default'",
    "UPDATE journal_drafts SET tenant_id = 'default' WHERE tenant_id IS NULL",
    "ALTER TABLE bank_transactions ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) DEFAULT 'default'",
    "UPDATE bank_transactions SET tenant_id = 'default' WHERE tenant_id IS NULL",
    "ALTER TABLE posting_logs ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) DEFAULT 'default'",
    "UPDATE posting_logs SET tenant_id = 'default' WHERE tenant_id IS NULL",
]

for sql in sqls:
    print("Running:", sql[:70])
    try:
        cur.execute(sql)
        print("OK")
    except Exception as e:
        print("Skip:", e)

print("Done!")
cur.close()
conn.close()
