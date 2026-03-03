from fastapi import APIRouter
from app.schemas.canonical import CanonicalBankTransaction
from app.engines.audit_engine import run_all_checks, get_issues, ISSUES

router = APIRouter(prefix="/audit", tags=["audit"])

@router.post("/check")
def audit_check(tx: CanonicalBankTransaction):
    issues = run_all_checks(tx)
    return {"ok": True, "count": len(issues), "issues": [i.model_dump() for i in issues]}

@router.get("/issues")
def list_issues(severity: str = ""):
    return {"ok": True, "count": len(get_issues(severity)), "issues": get_issues(severity)}

@router.post("/resolve/{issue_id}")
def resolve_issue(issue_id: str, resolved_by: str = "user"):
    for issue in ISSUES:
        if issue["id"] == issue_id:
            issue["status"] = "resolved"
            issue["resolved_by"] = resolved_by
            return {"ok": True, "issue_id": issue_id, "status": "resolved"}
    return {"ok": False, "error": "not found"}
