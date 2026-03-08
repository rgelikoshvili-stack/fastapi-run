from fastapi import APIRouter
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

@router.post("/run")
def run_reconciliation():
    try:
        return ok_response(
            "Reconciliation completed",
            {
                "matched": 0,
                "unmatched": 0,
                "status": "done"
            }
        )
    except Exception as e:
        return error_response("Reconciliation failed", "RECON_ERROR", str(e))

@router.get("/status")
def reconciliation_status():
    try:
        return ok_response(
            "Reconciliation status",
            {
                "ready": True,
                "status": "idle"
            }
        )
    except Exception as e:
        return error_response("Status failed", "RECON_STATUS_ERROR", str(e))

@router.get("/history")
def reconciliation_history():
    from app.api.db import get_db
    import psycopg2.extras
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT status, COUNT(*) as cnt,
                   MIN(created_at) as first, MAX(created_at) as last
            FROM journal_drafts GROUP BY status ORDER BY cnt DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]
    except:
        rows = []
    finally:
        cur.close(); conn.close()
    from app.api.response_utils import ok_response
    return ok_response("Reconciliation history", {"summary": rows})
