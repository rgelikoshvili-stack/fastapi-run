from fastapi import APIRouter, Request
from app.api.db import get_conn, _q
from app.api.services.pattern_decay_service import run_pattern_decay
from app.api.authz import require_permission
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/patterns", tags=["patterns"])


@router.get("/learning-health")
async def learning_health(request: Request):
    require_permission(request, "patterns:manage")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'active') AS active_count,
                COUNT(*) FILTER (WHERE status = 'candidate') AS candidate_count,
                COUNT(*) FILTER (WHERE status = 'inactive') AS inactive_count,
                COUNT(*) FILTER (
                    WHERE status = 'active'
                      AND last_seen_at IS NOT NULL
                      AND last_seen_at < NOW() - INTERVAL '45 days'
                ) AS stale_active_count,
                COUNT(*) FILTER (
                    WHERE status = 'active'
                      AND success_count >= 3
                      AND failure_count = 0
                      AND support_count >= 5
                      AND last_seen_at IS NOT NULL
                      AND last_seen_at >= NOW() - INTERVAL '45 days'
                ) AS autopilot_ready_count
            FROM learning_patterns
            WHERE tenant_id = %s
        """), tenant_id)

    return {
        "ok": True,
        "data": {
            "total_patterns": row["total"] or 0,
            "active_patterns": row["active_count"] or 0,
            "candidate_patterns": row["candidate_count"] or 0,
            "inactive_patterns": row["inactive_count"] or 0,
            "stale_active_patterns": row["stale_active_count"] or 0,
            "autopilot_ready_patterns": row["autopilot_ready_count"] or 0,
        },
    }


@router.post("/decay/run")
def decay_run():
    require_permission(request, "patterns:manage")
    result = run_pattern_decay()
    return {
        "ok": True,
        "data": result,
    }
