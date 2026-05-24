from fastapi import APIRouter, Query, Request
from app.schemas.canonical import CanonicalBankTransaction
from app.engines.audit_engine import run_all_checks, get_issues, ISSUES
from app.api.authz import require_permission

router = APIRouter(prefix="/audit", tags=["audit"])


@router.post("/check")
def audit_check(tx: CanonicalBankTransaction, request: Request):
    require_permission(request, "audit:view")
    issues = run_all_checks(tx)
    return {
        "ok": True,
        "count": len(issues),
        "issues": [i.model_dump() for i in issues],
    }


@router.get("/issues")
def list_issues(request: Request, severity: str = ""):
    require_permission(request, "audit:view")
    return {
        "ok": True,
        "count": len(get_issues(severity)),
        "issues": get_issues(severity),
    }


@router.get("/log")
def get_audit_log(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "audit:view")
    items = ISSUES[offset:offset + limit]
    return {
        "ok": True,
        "message": "Audit log fetched successfully",
        "data": {
            "items": items,
            "total": len(ISSUES),
            "limit": limit,
            "offset": offset,
        },
        "error": None,
    }


@router.post("/resolve/{issue_id}")
def resolve_issue(issue_id: str, request: Request, resolved_by: str = "user"):
    require_permission(request, "audit:view")
    for issue in ISSUES:
        if issue["id"] == issue_id:
            issue["status"] = "resolved"
            issue["resolved_by"] = resolved_by
            return {
                "ok": True,
                "issue_id": issue_id,
                "status": "resolved",
            }

    return {
        "ok": False,
        "error": "not found",
    }