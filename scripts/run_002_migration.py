"""Run Migration 002: Row Level Security."""
# SEC-1: Hardcoded production credentials removed.
# Set DB_HOST and DB_PASSWORD via environment variables.
# This script must only run against a non-production database.
import os, sys, psycopg2
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_KNOWN_PRODUCTION_HOSTS = {"35.192.214.120"}

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
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

    conn = psycopg2.connect(host=host, dbname=dbname, user=user, password=password)
else:
    conn = psycopg2.connect(DATABASE_URL)

SQL_FILE = Path(__file__).parent.parent / "app/storage/migrations/002_row_level_security.sql"
sql = SQL_FILE.read_text(encoding="utf-8")

conn.autocommit = True
try:
    with conn.cursor() as cur:
        cur.execute(sql)
    print("Migration 002 completed successfully.")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT tablename, rowsecurity
            FROM pg_tables
            WHERE tablename IN ('journal_drafts','counterparties','processed_documents')
            ORDER BY tablename
        """)
        print("RLS status:")
        for r in cur.fetchall():
            print(f"  {r[0]}: rls_enabled={r[1]}")
except Exception as e:
    print(f"Migration failed: {e}", file=sys.stderr)
    sys.exit(1)
finally:
    conn.close()
