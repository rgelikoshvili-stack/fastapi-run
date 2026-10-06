import hashlib
import psycopg2
import psycopg2.extras

from app.api.db import get_db, tenant_db_context_sync

def build_fingerprint(date, description, amount):
    raw = f"{date}|{description}|{amount}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def main():
    # tenants is control-plane metadata; each protected-table pass is scoped
    # separately using its server-read tenant identity.
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_id FROM tenants "
                "WHERE tenant_id IS NOT NULL AND btrim(tenant_id) <> '' "
                "AND lower(btrim(tenant_id)) <> 'default'"
            )
            tenant_ids = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    updated = 0
    for tenant_id in tenant_ids:
        with tenant_db_context_sync(tenant_id):
            conn = get_db(tenant_id)
            try:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute("""
                    SELECT id, normalized_date, normalized_description, normalized_amount
                    FROM journal_drafts
                    WHERE tenant_id = %s AND tx_fingerprint IS NULL
                """, (tenant_id,))
                rows = cur.fetchall()
                for row in rows:
                    fingerprint = build_fingerprint(
                        row["normalized_date"],
                        row["normalized_description"],
                        row["normalized_amount"],
                    )
                    cur.execute(
                        "UPDATE journal_drafts SET tx_fingerprint = %s "
                        "WHERE id = %s AND tenant_id = %s",
                        (fingerprint, row["id"], tenant_id),
                    )
                    updated += cur.rowcount
                conn.commit()
                cur.close()
            finally:
                conn.close()

    print(f"Updated fingerprints: {updated}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
