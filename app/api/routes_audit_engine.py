import logging
from fastapi import APIRouter, Request
import json
from datetime import datetime
from app.api.db import get_conn, _q
from app.api.tenant_context import resolve_tenant_id
from app.api.authz import require_permission
log = logging.getLogger(__name__)


router = APIRouter(prefix="/audit-engine", tags=["audit-engine"])


@router.get("/duplicates")
async def find_duplicates(request: Request):
    require_permission(request, "audit:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q("""
            SELECT filename, COUNT(*) as count, array_agg(run_id) as ids
            FROM pipeline_runs
            WHERE tenant_id = %s
            GROUP BY filename
            HAVING COUNT(*) > 1
            ORDER BY count DESC
        """), tenant_id)]
    return {"ok": True, "duplicates_found": len(rows), "items": rows}


@router.get("/anomalies")
async def find_anomalies(request: Request):
    require_permission(request, "audit:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    issues = []
    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q("""
            SELECT run_id, filename, extraction, state, created_at
            FROM pipeline_runs
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT 100
        """), tenant_id)]
    for r in rows:
        try:
            extraction = json.loads(r.get("extraction") or "{}")
            for a in extraction.get("amounts", []):
                v = a.get("value", 0)
                if v > 100000:
                    issues.append({"type": "HIGH_AMOUNT", "run_id": r["run_id"],
                                   "filename": r["filename"], "amount": v, "severity": "HIGH"})
                if v < 0:
                    issues.append({"type": "NEGATIVE_AMOUNT", "run_id": r["run_id"],
                                   "filename": r["filename"], "amount": v, "severity": "CRITICAL"})
        except Exception as e:
            log.warning("unexpected error: %s", e)
    return {"ok": True, "anomalies_found": len(issues), "issues": issues}


@router.get("/policy-check")
async def policy_check(request: Request):
    require_permission(request, "audit:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    violations = []
    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q("""
            SELECT run_id, filename, state, created_at
            FROM pipeline_runs
            WHERE state = 'PENDING_APPROVAL' AND tenant_id = %s
            ORDER BY created_at DESC
        """), tenant_id)]
    for r in rows:
        try:
            created_at = r["created_at"]
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            age_hours = (datetime.utcnow() - created_at.replace(tzinfo=None)).total_seconds() / 3600
            if age_hours > 48:
                violations.append({"type": "APPROVAL_OVERDUE", "run_id": r["run_id"],
                                    "filename": r["filename"], "hours_pending": round(age_hours, 1),
                                    "severity": "MEDIUM"})
        except Exception as e:
            log.warning("unexpected error: %s", e)
    return {"ok": True, "violations_found": len(violations), "violations": violations}


@router.get("/summary")
async def audit_summary(request: Request):
    require_permission(request, "audit:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        status_rows = await conn.fetch(_q(
            "SELECT state, COUNT(*) as count FROM pipeline_runs WHERE tenant_id = %s GROUP BY state"), tenant_id)
        status_counts = {r["state"]: r["count"] for r in status_rows}
        total = await conn.fetchval(_q("SELECT COUNT(*) FROM pipeline_runs WHERE tenant_id = %s"), tenant_id) or 0
        dups_row = await conn.fetchrow(_q("""
            SELECT COUNT(*) as dups FROM (
                SELECT filename FROM pipeline_runs WHERE tenant_id = %s
                GROUP BY filename HAVING COUNT(*) > 1
            ) x
        """), tenant_id)
        dups = dups_row["dups"] if dups_row else 0
    return {"ok": True, "total_runs": total, "status_breakdown": status_counts,
            "duplicate_filenames": dups, "health": "OK" if dups == 0 else "WARNING"}
