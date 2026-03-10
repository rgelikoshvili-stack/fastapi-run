@router.get("/queue")
def get_queue(status: str = "", limit: int = 100, offset: int = 0):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if status:
            cur.execute("""
                SELECT COUNT(*) AS total
                FROM journal_drafts
                WHERE status = %s
            """, (status,))
            total = cur.fetchone()["total"]

            cur.execute("""
                SELECT *
                FROM journal_drafts
                WHERE status = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s OFFSET %s
            """, (status, limit, offset))
        else:
            cur.execute("""
                SELECT COUNT(*) AS total
                FROM journal_drafts
                WHERE status IN ('drafted','pending_approval')
            """)
            total = cur.fetchone()["total"]

            cur.execute("""
                SELECT *
                FROM journal_drafts
                WHERE status IN ('drafted','pending_approval')
                ORDER BY created_at DESC, id DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))

        items = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return error_response("Queue failed", "QUEUE_ERROR", str(e))
    finally:
        cur.close(); conn.close()

    return ok_response("Approval queue", {
        "count": total,
        "filter": status or "drafted+pending_approval",
        "limit": limit,
        "offset": offset,
        "queue": items
    })