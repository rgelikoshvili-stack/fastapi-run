"""
app/api/routes_ocr.py
Bridge Hub — Invoice OCR Routes
"""
from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from app.api.tenant_context import resolve_tenant_id
from app.api.services.ocr_service import extract_invoice_fields, create_draft_from_invoice

router = APIRouter(prefix="/ocr", tags=["ocr"])


@router.post("/extract")
async def extract_from_file(
    request: Request,
    file: UploadFile = File(...),
):
    """
    PDF/Excel/სურათიდან ინვოისის ველების ამოღება.
    Draft არ იქმნება — მხოლოდ extraction.
    """
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    if not file.filename:
        raise HTTPException(status_code=400, detail="ფაილი სავალდებულოა")

    allowed = (".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg")
    if not any(file.filename.lower().endswith(ext) for ext in allowed):
        raise HTTPException(
            status_code=400,
            detail=f"დასაშვები ფორმატები: {', '.join(allowed)}"
        )

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="ფაილი 10MB-ზე მეტია")

    fields = extract_invoice_fields(file.filename, data)

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "filename": file.filename,
        "fields": fields,
    }


@router.post("/extract-and-draft")
async def extract_and_create_draft(
    request: Request,
    file: UploadFile = File(...),
):
    """
    PDF/Excel-იდან ინვოისის ამოღება + Draft-ის ავტომატური შექმნა.
    """
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    if not file.filename:
        raise HTTPException(status_code=400, detail="ფაილი სავალდებულოა")

    data = await file.read()
    fields = extract_invoice_fields(file.filename, data)

    if not fields.get("ok"):
        return {"ok": False, "error": "ინვოისიდან მონაცემების ამოღება ვერ მოხდა"}

    if not fields.get("amount"):
        return {
            "ok": False,
            "error": "თანხა ვერ ამოიღო",
            "fields": fields,
        }

    draft = create_draft_from_invoice(fields, tenant_id=tenant_id)

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "filename": file.filename,
        "extracted_fields": fields,
        "draft": draft,
    }


@router.get("/status")
def ocr_status():
    """
    OCR სისტემის სტატუსი.
    """
    try:
        import fitz
        pdf_support = True
    except Exception:
        pdf_support = False

    try:
        from openpyxl import load_workbook
        excel_support = True
    except Exception:
        excel_support = False

    return {
        "ok": True,
        "ocr_status": "active",
        "pdf_support": pdf_support,
        "excel_support": excel_support,
        "google_vision": "available_on_cloud_run",
        "supported_formats": [".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg"],
    }