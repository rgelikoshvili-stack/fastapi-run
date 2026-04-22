from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.api.tenant_context import resolve_tenant_id
from app.api.security import limiter
from app.api.services.export_service import (
    export_excel,
    export_csv_drafts,
    export_1c_xml,
    export_pdf,
)
from datetime import datetime

router = APIRouter(prefix="/export/v2", tags=["export-v2"])


@router.get("/journal/excel")
@limiter.limit("20/minute")
def journal_excel(request: Request, status: str = None):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    output = export_excel(tenant_id, status)
    filename = f"journal_{tenant_id}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/journal/csv")
@limiter.limit("20/minute")
def journal_csv(request: Request, status: str = None):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    output = export_csv_drafts(tenant_id, status)
    filename = f"journal_{tenant_id}_{datetime.now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/journal/1c-xml")
@limiter.limit("10/minute")
def journal_1c_xml(request: Request, status: str = "approved"):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    xml = export_1c_xml(tenant_id, status)
    filename = f"1c_export_{tenant_id}_{datetime.now().strftime('%Y%m%d')}.xml"
    return StreamingResponse(
        iter([xml.encode("utf-8")]),
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/journal/pdf")
@limiter.limit("10/minute")
def journal_pdf(request: Request, status: str = None):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    output = export_pdf(tenant_id, status)
    filename = f"journal_{tenant_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/available")
def available_exports(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "exports": [
            {"name": "Journal Excel", "endpoint": "/export/v2/journal/excel", "format": "XLSX"},
            {"name": "Journal CSV", "endpoint": "/export/v2/journal/csv", "format": "CSV"},
            {"name": "Journal PDF", "endpoint": "/export/v2/journal/pdf", "format": "PDF"},
            {"name": "1C XML", "endpoint": "/export/v2/journal/1c-xml", "format": "XML"},
        ]
    }