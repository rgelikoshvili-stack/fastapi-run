from fastapi import APIRouter
import psycopg2, psycopg2.extras, json
from datetime import datetime
from app.api.db import get_db

router = APIRouter(prefix="/audit-engine", tags=["audit-engine"])



@router.get("/duplicates")
def find_duplicates():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT filename, COUNT(*) as count, array_agg(run_id) as ids
        FROM pipeline_runs
        GROUP BY filename
        HAVING COUNT(*) > 1
        ORDER BY count DESC
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return {"ok": True, "duplicates_found": len(rows), "items": [dict(r) for r in rows]}

@router.get("/anomalies")
def find_anomalies():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    issues = []
    cur.execute("SELECT run_id, filename, extraction, state, created_at FROM pipeline_runs ORDER BY created_at DESC LIMIT 100")
    rows = cur.fetchall()
    for row in rows:
        r = dict(row)
        try:
            extraction = json.loads(r.get("extraction_result") or "{}")
            amounts = extraction.get("amounts", [])
            for a in amounts:
                v = a.get("value", 0)
                if v > 100000:
                    issues.append({"type": "HIGH_AMOUNT", "run_id": r["run_id"], "filename": r["filename"], "amount": v, "severity": "HIGH"})
                if v < 0:
                    issues.append({"type": "NEGATIVE_AMOUNT", "run_id": r["run_id"], "filename": r["filename"], "amount": v, "severity": "CRITICAL"})
        except:
            pass
    cur.close(); conn.close()
    return {"ok": True, "anomalies_found": len(issues), "issues": issues}

@router.get("/policy-check")
def policy_check():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    violations = []
    cur.execute("SELECT run_id, filename, state, created_at FROM pipeline_runs WHERE state='PENDING_APPROVAL' ORDER BY created_at DESC")
    rows = cur.fetchall()
    for row in rows:
        r = dict(row)
        age_hours = (datetime.utcnow() - datetime.fromisoformat(str(r["created_at"])).replace(tzinfo=None)).total_seconds() / 3600
        if age_hours > 48:
            violations.append({"type": "APPROVAL_OVERDUE", "run_id": r["run_id"], "filename": r["filename"], "hours_pending": round(age_hours, 1), "severity": "MEDIUM"})
    cur.close(); conn.close()
    return {"ok": True, "violations_found": len(violations), "violations": violations}

@router.get("/summary")
def audit_summary():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT state, COUNT(*) as count FROM pipeline_runs GROUP BY state")
    status_counts = {r["state"]: r["count"] for r in cur.fetchall()}
    cur.execute("SELECT COUNT(*) as total FROM pipeline_runs")
    total = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as dups FROM (SELECT filename FROM pipeline_runs GROUP BY filename HAVING COUNT(*)>1) x")
    dups = cur.fetchone()["dups"]
    cur.close(); conn.close()
    return {"ok": True, "total_runs": total, "status_breakdown": status_counts, "duplicate_filenames": dups, "health": "OK" if dups == 0 else "WARNING"}