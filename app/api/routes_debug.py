from fastapi import APIRouter, Request
import os

from app.api.db import get_conn, _q
from app.api.authz import require_permission
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/debug", tags=["debug"])


def _require_debug_access(request: Request) -> None:
    require_permission(request, "tenants:manage")


@router.get("/log")
async def debug_log(request: Request, limit: int = 20):
    _require_debug_access(request)
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
def debug_openai(request: Request):
    _require_debug_access(request)
    api_key = (os.getenv("OPENAI_API_KEY", "") or "").strip()
    return ok_response("OpenAI debug", {"configured": bool(api_key)})


@router.get("/balance-ping")
def debug_balance_ping(request: Request):
    _require_debug_access(request)
    base_url = (os.getenv("BALANCE_API_URL", "") or "").strip()
    api_key = (os.getenv("BALANCE_API_KEY", "") or "").strip()
    company_id = (os.getenv("BALANCE_COMPANY_ID", "") or "").strip()
    return ok_response(
        "Balance config debug",
        {
            "base_url_configured": bool(base_url),
            "api_key_configured": bool(api_key),
            "company_id_configured": bool(company_id),
        },
    )


@router.get("/ai-routing")
def debug_ai_routing(request: Request):
    """Returns which knowledge buckets are loaded and how PDF routing works."""
    _require_debug_access(request)
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


_ANTHROPIC_MODEL = "claude-sonnet-4-6"
_OPENROUTER_MODEL = "openai/gpt-4o-mini"
_LLM_TIMEOUT = 10  # seconds


def _safe_error(exc: Exception) -> str:
    """Return a generic error label — never leaks key/URL/config details."""
    name = type(exc).__name__
    msg = str(exc)
    # Map known SDK error classes to stable codes
    for marker, code in (
        ("AuthenticationError", "AUTH_ERROR"),
        ("PermissionDenied",    "AUTH_ERROR"),
        ("RateLimitError",      "RATE_LIMIT"),
        ("APIConnectionError",  "CONNECTION_ERROR"),
        ("APITimeoutError",     "TIMEOUT"),
        ("Timeout",             "TIMEOUT"),
        ("NotFoundError",       "MODEL_NOT_FOUND"),
        ("BadRequestError",     "BAD_REQUEST"),
        ("InternalServerError", "PROVIDER_ERROR"),
    ):
        if marker in name or marker in msg:
            return code
    return "PROVIDER_ERROR"


async def _ping_anthropic() -> dict:
    import asyncio
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"ok": False, "model": _ANTHROPIC_MODEL, "error": "NOT_CONFIGURED"}
    try:
        import anthropic as _ant
        client = _ant.AsyncAnthropic(api_key=api_key)
        resp = await asyncio.wait_for(
            client.messages.create(
                model=_ANTHROPIC_MODEL,
                max_tokens=10,
                messages=[{"role": "user", "content": "Return exactly ANTHROPIC_OK"}],
            ),
            timeout=_LLM_TIMEOUT,
        )
        text = (resp.content[0].text or "").strip() if resp.content else ""
        return {"ok": "ANTHROPIC_OK" in text, "model": _ANTHROPIC_MODEL, "error": None}
    except Exception as exc:
        return {"ok": False, "model": _ANTHROPIC_MODEL, "error": _safe_error(exc)}


async def _ping_openrouter() -> dict:
    import asyncio
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return {"ok": False, "model": _OPENROUTER_MODEL, "error": "NOT_CONFIGURED"}
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=_OPENROUTER_MODEL,
                max_tokens=10,
                messages=[{"role": "user", "content": "Return exactly OPENROUTER_OK"}],
            ),
            timeout=_LLM_TIMEOUT,
        )
        text = (resp.choices[0].message.content or "").strip() if resp.choices else ""
        return {"ok": "OPENROUTER_OK" in text, "model": _OPENROUTER_MODEL, "error": None}
    except Exception as exc:
        return {"ok": False, "model": _OPENROUTER_MODEL, "error": _safe_error(exc)}


@router.get("/llm-ping")
async def debug_llm_ping(request: Request):
    """Live LLM provider ping — verifies real API calls, not just env var presence."""
    _require_debug_access(request)
    import asyncio
    anthropic_result, openrouter_result = await asyncio.gather(
        _ping_anthropic(),
        _ping_openrouter(),
    )
    return {
        "anthropic":   anthropic_result,
        "openrouter":  openrouter_result,
    }


@router.get("/kb-files")
async def debug_kb_files(request: Request):
    _require_debug_access(request)
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
