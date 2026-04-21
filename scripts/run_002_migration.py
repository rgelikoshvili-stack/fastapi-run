"""Run Migration 002: Row Level Security."""
import os, sys, psycopg2
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "35.192.214.120"),
        dbname=os.getenv("DB_NAME", "bridgehub"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "BridgeHub2026x"),
    )
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
