from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
import io, csv, json
from datetime import datetime
from app.api.db import get_conn, _q
from app.api.authz import require_permission

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/documents/csv")
async def export_documents_csv(request: Request):
    require_permission(request, "export:any")
    # pipeline_runs is a global table without tenant_id — exported as-is
    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(
            "SELECT id, filename, status, created_at FROM pipeline_runs ORDER BY created_at DESC"
        )]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id","filename","status","created_at"])
    writer.writeheader()
    for r in rows:
        writer.writerow({"id": r["id"], "filename": r["filename"],
                         "status": r["status"], "created_at": str(r["created_at"])})
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=documents_{datetime.now().strftime('%Y%m%d')}.csv"})


@router.get("/transactions/csv")
async def export_transactions_csv(request: Request):
    require_permission(request, "export:any")
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q(
            "SELECT id, bank, date, amount, description, balance FROM bank_transactions WHERE tenant_id=%s ORDER BY created_at DESC"
        ), tenant_id)]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id","bank","date","amount","description","balance"])
    writer.writeheader()
    for r in rows:
        writer.writerow(dict(r))
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=transactions_{datetime.now().strftime('%Y%m%d')}.csv"})


@router.get("/coa/csv")
async def export_coa_csv(request: Request):
    require_permission(request, "export:any")
    # Chart of accounts is global reference data without tenant_id
    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(
            "SELECT code, name_ka, name_en, category, direction FROM coa ORDER BY code"
        )]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["code","name_ka","name_en","category","direction"])
    writer.writeheader()
    for r in rows:
        writer.writerow(dict(r))
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=coa_{datetime.now().strftime('%Y%m%d')}.csv"})


@router.get("/report/json")
async def export_full_report_json(request: Request):
    require_permission(request, "export:any")
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        total_docs = await conn.fetchval("SELECT COUNT(*) FROM pipeline_runs") or 0
        status_rows = await conn.fetch("SELECT status, COUNT(*) as count FROM pipeline_runs GROUP BY status")
        status_breakdown = {r["status"]: r["count"] for r in status_rows}
        inflow = float(await conn.fetchval(_q(
            "SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) FROM bank_transactions WHERE tenant_id=%s"
        ), tenant_id) or 0)
        outflow = float(await conn.fetchval(_q(
            "SELECT COALESCE(SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END),0) FROM bank_transactions WHERE tenant_id=%s"
        ), tenant_id) or 0)
        total_txs = await conn.fetchval(_q(
            "SELECT COUNT(*) FROM bank_transactions WHERE tenant_id=%s"
        ), tenant_id) or 0
        monthly_rows = await conn.fetch(_q("""
            SELECT DATE_TRUNC('month', created_at) as month,
                SUM(CASE WHEN amount>0 THEN amount ELSE 0 END) as inflow,
                SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END) as outflow
            FROM bank_transactions WHERE tenant_id=%s GROUP BY month ORDER BY month DESC LIMIT 12
        """), tenant_id)
        monthly = [{"month": str(r["month"])[:7], "inflow": round(float(r["inflow"]),2),
                    "outflow": round(float(r["outflow"]),2)} for r in monthly_rows]

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "tenant_id": tenant_id,
        "summary": {
            "total_documents": total_docs,
            "status_breakdown": status_breakdown,
            "total_transactions": total_txs,
            "total_inflow_gel": round(inflow, 2),
            "total_outflow_gel": round(outflow, 2),
            "net_cashflow_gel": round(inflow - outflow, 2),
        },
        "monthly_cashflow": monthly,
    }
    output = io.BytesIO(json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
    return StreamingResponse(output,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=report_{datetime.now().strftime('%Y%m%d')}.json"})


@router.get("/available")
def available_exports(request: Request):
    require_permission(request, "export:any")
    return {
        "ok": True,
        "exports": [
            {"name": "Documents CSV", "endpoint": "/export/documents/csv", "format": "CSV"},
            {"name": "Transactions CSV", "endpoint": "/export/transactions/csv", "format": "CSV"},
            {"name": "COA CSV", "endpoint": "/export/coa/csv", "format": "CSV"},
            {"name": "Full Report JSON", "endpoint": "/export/report/json", "format": "JSON"},
        ],
    }
