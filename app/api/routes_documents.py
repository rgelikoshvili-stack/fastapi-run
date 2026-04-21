"""app/api/routes_documents.py
Document upload + intelligence pipeline:
  parse → extract → resolve party → classify operation → build journal
"""
import hashlib
import json
import logging
from fastapi import APIRouter, UploadFile, File, Request
from fastapi.responses import JSONResponse

from app.api.tenant_context import resolve_tenant_id
from app.api.response_utils import ok_response, error_response
from app.api.db import get_db
from app.api.services.document_parser import parse_document
from app.api.services.document_extractor import extract_document, ExtractedDocument
from app.api.services.party_resolver import resolve_party, OurRole
from app.api.services.operation_classifier import classify_operation_async
from app.api.services.doc_journal_builder import build_journal

router = APIRouter(prefix="/documents", tags=["documents"])
log = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _confidence_score(parsed: dict, extracted: ExtractedDocument, party, cat_confidence: float) -> float:
    score = 0.0
    method_scores = {
        "native_pdf": 0.40, "tesseract_pdf": 0.30,
        "tesseract_image": 0.30, "vision_llm": 0.25,
        "tesseract_pdf_low_quality": 0.15, "tesseract_image_low_quality": 0.15,
    }
    score += method_scores.get(parsed.get("method", ""), 0.20)

    if extracted.seller.inn and extracted.buyer.inn:
        score += 0.20
    elif extracted.seller.inn or extracted.buyer.inn:
        score += 0.10

    if extracted.total_with_vat:
        score += 0.05
    if extracted.document_series and extracted.document_number:
        score += 0.05

    if party.our_role in (OurRole.BUYER, OurRole.SELLER):
        score += 0.20
    elif party.our_role == OurRole.FOREIGN:
        score += 0.15

    score += cat_confidence * 0.10
    return round(min(score, 1.0), 2)


def _get_tenant_vat(tenant_id: str) -> bool:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT is_vat_payer FROM tenants WHERE tenant_id = %s", (tenant_id,))
        row = cur.fetchone()
        return bool(row[0]) if row else True
    finally:
        cur.close()
        conn.close()


def _upsert_counterparty(tenant_id: str, inn: str, name: str, cp_type: str) -> None:
    if not inn:
        return
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO counterparties (tenant_id, inn, name, type, total_transactions, last_transaction_at)
            VALUES (%s, %s, %s, %s, 1, NOW())
            ON CONFLICT (tenant_id, inn) DO UPDATE SET
                total_transactions = counterparties.total_transactions + 1,
                last_transaction_at = NOW(),
                name = EXCLUDED.name
            """,
            (tenant_id, inn, name or inn, cp_type),
        )
        conn.commit()
    except Exception as e:
        log.warning("counterparty upsert failed: %s", e)
        conn.rollback()
    finally:
        cur.close()
        conn.close()


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), request: Request = None):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None) if request else None)

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        return JSONResponse(status_code=413, content={"ok": False, "error": "File too large (max 10MB)"})

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    mime_type = file.content_type or "application/pdf"

    # ── 1. Dedup by file hash ──────────────────────────────────────────────
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM processed_documents WHERE tenant_id = %s AND file_hash = %s",
        (tenant_id, file_hash),
    )
    existing_file = cur.fetchone()
    cur.close()
    conn.close()

    if existing_file:
        conn2 = get_db()
        cur2 = conn2.cursor()
        cur2.execute(
            "SELECT id, status FROM journal_drafts WHERE source_document_id = %s LIMIT 1",
            (existing_file[0],),
        )
        existing_draft = cur2.fetchone()
        cur2.close()
        conn2.close()
        return ok_response("Duplicate file", {
            "status": "duplicate_file",
            "message": "ეს ფაილი უკვე ატვირთულია",
            "existing_draft_id": existing_draft[0] if existing_draft else None,
        })

    # ── 2. Parse text ──────────────────────────────────────────────────────
    llm_service = None
    try:
        from app.api.services.llm_service import llm_service as _llm
        llm_service = _llm
    except Exception:
        pass

    parsed = await parse_document(file_bytes, mime_type, llm_service)

    # ── 3. Extract structured data ─────────────────────────────────────────
    extracted = await extract_document(parsed.get("text", ""), llm_service)

    # ── 4. Save processed document record ─────────────────────────────────
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO processed_documents
                (tenant_id, file_hash, file_name, file_size_bytes, mime_type,
                 extraction_method, raw_text, extracted_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                tenant_id, file_hash, file.filename, len(file_bytes),
                mime_type, parsed.get("method"),
                (parsed.get("text") or "")[:10000],
                json.dumps(extracted.dict()),
            ),
        )
        doc_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        log.error("processed_documents insert failed: %s", e)
        return error_response("DB error", "DB_ERROR", str(e))
    finally:
        cur.close()
        conn.close()

    # ── 5. Dedup by document series+number ────────────────────────────────
    if extracted.document_series and extracted.document_number:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, status FROM journal_drafts
            WHERE tenant_id = %s AND document_series = %s
              AND document_number = %s AND status != 'rejected'
            LIMIT 1
            """,
            (tenant_id, extracted.document_series, extracted.document_number),
        )
        dup = cur.fetchone()
        cur.close()
        conn.close()
        if dup:
            return ok_response("Duplicate document", {
                "status": "duplicate_document",
                "message": f"ეს სასაქონლო-ზედნადები უკვე არსებობს (draft #{dup[0]})",
                "existing_draft_id": dup[0],
                "existing_status": dup[1],
                "extracted": extracted.dict(),
            })

    # ── 6. Resolve party ───────────────────────────────────────────────────
    party = resolve_party(extracted, tenant_id)

    # ── 7. Foreign document — save + return early ──────────────────────────
    if party.our_role == OurRole.FOREIGN:
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO journal_drafts
                    (tenant_id, status, is_foreign_doc, our_role,
                     counterparty_inn, counterparty_name,
                     document_series, document_number, date,
                     amount, raw_extraction, source_document_id, journal_entries)
                VALUES (%s,'rejected_foreign',TRUE,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    tenant_id, party.our_role.value,
                    extracted.seller.inn, extracted.seller.name,
                    extracted.document_series, extracted.document_number,
                    extracted.issue_date,
                    extracted.total_with_vat,
                    json.dumps(extracted.dict()), doc_id,
                    json.dumps([]),
                ),
            )
            draft_id = cur.fetchone()[0]
            conn.commit()
        finally:
            cur.close()
            conn.close()

        return ok_response("Foreign document", {
            "status": "foreign_document",
            "draft_id": draft_id,
            "message": "ეს დოკუმენტი არ ეკუთვნის ჩვენი კომპანიის",
            "warnings": party.warnings,
            "extracted": extracted.dict(),
        })

    # ── 8. Classify operation ──────────────────────────────────────────────
    category, cat_confidence = await classify_operation_async(extracted, llm_service)

    # ── 9. Build journal entries ───────────────────────────────────────────
    is_vat_payer = _get_tenant_vat(tenant_id)
    journal = build_journal(extracted, party, category, is_vat_payer)

    # ── 10. Calculate confidence ───────────────────────────────────────────
    confidence = _confidence_score(parsed, extracted, party, cat_confidence)

    # ── 11. Insert draft ───────────────────────────────────────────────────
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO journal_drafts
                (tenant_id, status, our_role, operation_type, operation_category,
                 counterparty_inn, counterparty_name,
                 document_series, document_number, date,
                 amount, journal_entries, raw_extraction,
                 source_document_id, description)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                tenant_id, "pending",
                party.our_role.value, extracted.document_type, category.value,
                party.counterparty_inn, party.counterparty_name,
                extracted.document_series, extracted.document_number,
                extracted.issue_date,
                extracted.total_with_vat,
                json.dumps(journal["entries"]),
                json.dumps(extracted.dict()),
                doc_id,
                f"{extracted.document_type} — {party.counterparty_name or '?'}",
            ),
        )
        draft_id = cur.fetchone()[0]
        conn.commit()
    finally:
        cur.close()
        conn.close()

    # ── 12. Upsert counterparty ────────────────────────────────────────────
    _upsert_counterparty(
        tenant_id,
        party.counterparty_inn or "",
        party.counterparty_name or "",
        "vendor" if party.our_role == OurRole.BUYER else "customer",
    )

    log.info("action=document_uploaded tenant=%s draft_id=%s role=%s conf=%.2f method=%s",
             tenant_id, draft_id, party.our_role.value, confidence, parsed.get("method"))

    return ok_response("Document processed", {
        "status": "pending",
        "draft_id": draft_id,
        "confidence": confidence,
        "our_role": party.our_role.value,
        "counterparty": {
            "inn": party.counterparty_inn,
            "name": party.counterparty_name,
        },
        "operation_category": category.value,
        "journal_entries": journal["entries"],
        "extracted": extracted.dict(),
        "warnings": journal["warnings"],
        "extraction_method": parsed.get("method"),
    })
