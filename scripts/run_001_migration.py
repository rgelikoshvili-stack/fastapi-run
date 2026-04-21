"""Run Migration 001: multi-tenant schema with document intelligence fields."""
import os
import sys
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    host = os.getenv("DB_HOST", "35.192.214.120")
    dbname = os.getenv("DB_NAME", "bridgehub")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "BridgeHub2026x")
    conn = psycopg2.connect(host=host, dbname=dbname, user=user, password=password)
else:
    conn = psycopg2.connect(DATABASE_URL)

SQL_FILE = Path(__file__).parent.parent / "app/storage/migrations/001_multi_tenant_schema.sql"
sql = SQL_FILE.read_text(encoding="utf-8")

conn.autocommit = True
try:
    with conn.cursor() as cur:
        cur.execute(sql)
    print("Migration 001 completed successfully.")
    with conn.cursor() as cur:
        cur.execute("SELECT tenant_id, company_inn, company_name_legal FROM tenants LIMIT 5;")
        rows = cur.fetchall()
        print("\nTenants after migration:")
        for r in rows:
            print(f"  {r[0]} | inn={r[1]} | name={r[2]}")
except Exception as e:
    print(f"Migration failed: {e}", file=sys.stderr)
    sys.exit(1)
finally:
    conn.close()
