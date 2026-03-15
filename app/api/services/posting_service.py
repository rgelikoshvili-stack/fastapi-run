import psycopg2.extras
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response


def get_approved_drafts_service(limit: int, offset: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT *
            FROM journal_drafts
            WHERE status = 'approved'
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )

        rows = cur.fetchall()

    except Exception as e:
        return error_response("Load failed", "LOAD_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    return ok_response(
        "Approved drafts",
        {
            "count": len(rows),
            "items": rows,
        },
    )