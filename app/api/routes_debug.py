from fastapi import APIRouter, Request
import os

from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/log")
async def debug_log(request: Request, limit: int = 20):
    tenant_id = getattr(request.state, "tenant_id", "default")
    try:
        async with get_conn() as conn:
            rows = [dict(r) for r in await conn.fetch(_q("""
                SELECT id, event_type, actor, details, created_at
                FROM audit_events
                WHERE tenant_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """), tenant_id, limit)]
    except Exception as e:
        return error_response("Debug log failed", "DEBUG_LOG_ERROR", str(e))
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


@router.get("/ai-routing")
def debug_ai_routing():
    """Returns which knowledge buckets are loaded and how PDF routing works."""
    try:
        import app.knowledge.knowledge_loader as _kl
        _kl._load_files()  # no-op if already loaded; triggers load on first call
        tax_loaded = bool(_kl._TAX_TEXT and _kl._TAX_TEXT.strip())
        acc_loaded = bool(_kl._ACC_TEXT and _kl._ACC_TEXT.strip())
        tax_size = len(_kl._TAX_TEXT or "")
        acc_size = len(_kl._ACC_TEXT or "")
        tax_kw = list(_kl._TAX_FILENAME_KEYWORDS)
    except Exception as e:
        return ok_response("ai-routing", {"error": str(e), "loaded": False})

    anthropic_key = bool(os.getenv("ANTHROPIC_API_KEY"))

    return ok_response(
        "AI knowledge routing",
        {
            "buckets": {
                "TAX_TEXT": {"loaded": tax_loaded, "chars": tax_size},
                "ACC_TEXT": {"loaded": acc_loaded, "chars": acc_size},
            },
            "pdf_routing": {
                "rule": "filename contains keyword → TAX_TEXT, otherwise → ACC_TEXT",
                "tax_keywords": tax_kw,
            },
            "claude_available": anthropic_key,
            "status": "ok" if (tax_loaded or acc_loaded) else "no_files_loaded",
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
