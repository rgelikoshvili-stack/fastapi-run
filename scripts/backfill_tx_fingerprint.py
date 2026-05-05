"""Admin script: backfill tx_fingerprint for journal_drafts rows that are missing it.

Usage:
    # All tenants (admin use only):
    DATABASE_URL="postgresql://..." python scripts/backfill_tx_fingerprint.py

    # Single tenant:
    DATABASE_URL="postgresql://..." TENANT_ID="tenant-a" python scripts/backfill_tx_fingerprint.py
"""
import hashlib
import os
import psycopg2
import psycopg2.extras

from app.api.db import get_db


def build_fingerprint(date, description, amount):
    raw = f"{date}|{description}|{amount}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main():
    tenant_id = os.environ.get("TENANT_ID")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if tenant_id:
        cur.execute(
            """
            SELECT id, normalized_date, normalized_description, normalized_amount
            FROM journal_drafts
            WHERE tx_fingerprint IS NULL AND tenant_id = %s
            """,
            (tenant_id,),
        )
        print(f"Scope: tenant_id={tenant_id}")
    else:
        print("WARNING: running across ALL tenants. Set TENANT_ID env var to scope.")
        cur.execute(
            """
            SELECT id, normalized_date, normalized_description, normalized_amount
            FROM journal_drafts
            WHERE tx_fingerprint IS NULL
            """
        )

    rows = cur.fetchall()
    updated = 0

    for r in rows:
        fp = build_fingerprint(
            r["normalized_date"],
            r["normalized_description"],
            r["normalized_amount"],
        )
        cur.execute(
            "UPDATE journal_drafts SET tx_fingerprint = %s WHERE id = %s",
            (fp, r["id"]),
        )
        updated += 1

    conn.commit()
    print(f"Updated fingerprints: {updated}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
