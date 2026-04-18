from fastapi import APIRouter, Request
import os
import psycopg2.extras

from app.api.db import get_db
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/log")
def debug_log(request: Request, limit: int = 20):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """
            SELECT id, event_type, actor, details, created_at
            FROM audit_events
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (tenant_id, limit),
        )
        rows = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return error_response("Debug log failed", "DEBUG_LOG_ERROR", str(e))
    finally:
        cur.close()
        conn.close()
    return ok_response("Debug log", {"count": len(rows), "events": rows})


@router.get("/openai")
def debug_openai():
    api_key = (os.getenv("OPENAI_API_KEY", "") or "").strip()
    return ok_response(
        "OpenAI debug",
        {
            "configured": bool(api_key),
            "key_prefix": api_key[:10] if api_key else "",
            "length": len(api_key) if api_key else 0,
        },
    )


@router.get("/balance-ping")
def debug_balance_ping():
    base_url = (os.getenv("BALANCE_API_URL", "") or "").strip()
    api_key = (os.getenv("BALANCE_API_KEY", "") or "").strip()
    company_id = (os.getenv("BALANCE_COMPANY_ID", "") or "").strip()
    return ok_response(
        "Balance config debug",
        {
            "base_url": base_url,
            "api_key_configured": bool(api_key),
            "company_id": company_id,
        },
    )


@router.get("/kb-files")
async def debug_kb_files():
    paths = [
        "knowledge_files",
        "/app/knowledge_files",
        os.path.dirname(os.path.abspath(__file__)) + "/../../knowledge_files",
    ]
    result = {}
    for p in paths:
        try:
            abs_p = os.path.abspath(p)
            if os.path.exists(abs_p):
                files = os.listdir(abs_p)
                sizes = {f: os.path.getsize(os.path.join(abs_p, f)) for f in files}
                result[abs_p] = sizes
            else:
                result[p] = "NOT FOUND"
        except Exception as e:
            result[p] = f"ERROR: {e}"
    return result