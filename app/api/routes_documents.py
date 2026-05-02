"""app/api/routes_documents.py
Document upload + intelligence pipeline:
  parse → extract → resolve party → classify operation → build journal

Triangle document endpoints:
  POST /documents/upload-waybill
  POST /documents/upload-tax-invoice
  POST /documents/upload-commercial-invoice
"""
import asyncio
import hashlib
import json
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, UploadFile, File, Request, Query

from app.api.tenant_context import resolve_tenant_id
from app.api.response_utils import ok_response, error_response, http_error
from app.api.db import get_db
from app.api.security import limiter
from app.api.services.document_parser import parse_document
from app.api.services.document_extractor import extract_document, ExtractedDocument
from app.api.services.party_resolver import resolve_party, OurRole
from app.api.services.operation_classifier import classify_operation_async
from app.api.services.doc_journal_builder import build_journal
from app.api.services.triangle_matcher import compute_match_score, find_candidates, upsert_triangle_match
from app.api.services.correction_detector import detect_corrections, save_corrections
from app.api.services.storage_service import upload_file as gcs_upload, download_file as gcs_download, safe_download
from app.api.services.completeness_checker import check_document_set
from app.api.services.contract_classifier import classify_provider_type

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


import re as _re


def _parse_company_from_notes(notes: str) -> str | None:
    """Extract Georgian company name from raw OCR notes — prefers შპს over სს to avoid bank names."""
    if not notes:
        return None
    # Priority 1: შპს (LLC) — most common for private companies
    m = _re.search(r'შპს\s+([\w][^\n]{2,60})', notes, _re.UNICODE)
    if m:
        name = 'შპს ' + m.group(1).split('\n')[0].strip().rstrip('.,;:')
        name = _re.sub(r'\s+(INVOICE|invoice|ინვოისი|შეკვ|ზედნ).*', '', name, flags=_re.I).strip()
        if 6 < len(name) < 80:
            return name
    # Priority 2: ი/მ (sole trader)
    m = _re.search(r'ი/მ\s+([\w][^\n]{2,60})', notes, _re.UNICODE)
    if m:
        name = 'ი/მ ' + m.group(1).split('\n')[0].strip().rstrip('.,;:')
        if 6 < len(name) < 80:
            return name
    # Priority 3: სს — but exclude lines that are bank references ("ბანკი: სს ...")
    for m in _re.finditer(r'სს\s+([\w][^\n]{2,60})', notes, _re.UNICODE):
        line = notes[max(0, m.start()-15):m.start()]
        if 'ბანკი' in line or 'bank' in line.lower():
            continue
        name = 'სს ' + m.group(1).split('\n')[0].strip().rstrip('.,;:')
        if 6 < len(name) < 80:
            return name
    return None


def _resolve_seller_name(extracted: "ExtractedDocument", party) -> str:
    """Best available counterparty name — falls back to notes parsing."""
    name = (
        party.counterparty_name
        or extracted.seller.name
        or extracted.buyer.name
    )
    if not name:
        name = _parse_company_from_notes(extracted.notes or "")
    return name or ""


def _build_description(extracted: "ExtractedDocument", party, draft_id: int = None, amount=None) -> str:
    """Draft description: Company (INN)."""
    company = _resolve_seller_name(extracted, party)
    inn = party.counterparty_inn or extracted.seller.inn or extracted.seller_inn or ""
    if company and inn:
        return f"{company} ({inn})"
    return company or inn or "?"


def _build_partner(extracted: "ExtractedDocument", party) -> str:
    """Partner field: invoice number."""
    doc_num = extracted.document_number or extracted.document_series
    return f"№{doc_num}" if doc_num else ""


def _get_tenant_vat(tenant_id: str) -> bool:
    conn = get_db(tenant_id)
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
    conn = get_db(tenant_id)
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
@limiter.limit("10/minute")
async def upload_document(file: UploadFile = File(...), request: Request = None):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None) if request else None)

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        return http_error(413, "File too large (max 10MB)", "FILE_TOO_LARGE")

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    mime_type = file.content_type or "application/pdf"

    # ── 1. Dedup by file hash ──────────────────────────────────────────────
    conn = get_db(tenant_id)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, (file_content IS NOT NULL OR gcs_path IS NOT NULL) AS has_content FROM processed_documents WHERE tenant_id = %s AND file_hash = %s",
        (tenant_id, file_hash),
    )
    existing_file = cur.fetchone()
    cur.close()
    conn.close()

    if existing_file and existing_file[1]:
        # File already stored — check if the linked draft is still active
        doc_id_existing = existing_file[0]
        conn2 = get_db(tenant_id)
        cur2 = conn2.cursor()
        cur2.execute(
            "SELECT id, status FROM journal_drafts WHERE source_document_id = %s ORDER BY id DESC LIMIT 1",
            (doc_id_existing,),
        )
        existing_draft = cur2.fetchone()
        cur2.close()
        conn2.close()

        _terminal = {'rejected', 'posted', 'auto_approved'}
        draft_is_terminal = (existing_draft is None) or (existing_draft[1] in _terminal)

        if not draft_is_terminal:
            # Draft is still actionable — real duplicate
            return ok_response("Duplicate file", {
                "status": "duplicate_file",
                "message": "ეს ფაილი უკვე ატვირთულია",
                "existing_draft_id": existing_draft[0] if existing_draft else None,
            })
        # Draft was rejected/deleted — re-trigger pipeline on the existing stored file
        asyncio.create_task(
            _process_document_background(doc_id_existing, tenant_id, file_bytes, mime_type, file.filename or "document")
        )
        return ok_response("Re-processing file", {
            "status": "reprocessing",
            "message": "ფაილი ხელახლა მუშავდება",
            "doc_id": doc_id_existing,
        })

    if existing_file and not existing_file[1]:
        # Record exists but content was never stored — patch it
        doc_id = existing_file[0]
        gcs_path = gcs_upload(file_bytes, file.filename or "document", mime_type, tenant_id)
        conn_patch = get_db(tenant_id)
        cur_patch = conn_patch.cursor()
        try:
            if gcs_path:
                cur_patch.execute(
                    "UPDATE processed_documents SET gcs_path = %s WHERE id = %s AND tenant_id = %s",
                    (gcs_path, doc_id, tenant_id),
                )
            else:
                cur_patch.execute(
                    "UPDATE processed_documents SET file_content = %s WHERE id = %s AND tenant_id = %s",
                    (file_bytes, doc_id, tenant_id),
                )
            conn_patch.commit()
        finally:
            cur_patch.close()
            conn_patch.close()
        log.info("action=doc_content_patched doc_id=%s tenant=%s", doc_id, tenant_id)
        conn2 = get_db(tenant_id)
        cur2 = conn2.cursor()
        cur2.execute(
            "SELECT id, status FROM journal_drafts WHERE source_document_id = %s LIMIT 1",
            (doc_id,),
        )
        existing_draft = cur2.fetchone()
        cur2.close()
        conn2.close()
        return ok_response("File content restored", {
            "status": "content_restored",
            "message": "ფაილის შინაარსი განახლდა — 👁 ღილაკი ახლა მუშაობს",
            "doc_id": doc_id,
            "existing_draft_id": existing_draft[0] if existing_draft else None,
        })

    # ── 2. Upload to GCS (or fall back to DB storage if GCS not configured) ──
    gcs_path = gcs_upload(file_bytes, file.filename or "document", mime_type, tenant_id)
    # gcs_path is None when GCS is unavailable → store bytes in file_content column

    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        if gcs_path:
            cur.execute(
                """
                INSERT INTO processed_documents
                    (tenant_id, file_hash, file_name, file_size_bytes, mime_type, gcs_path, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'processing')
                RETURNING id
                """,
                (tenant_id, file_hash, file.filename, len(file_bytes), mime_type, gcs_path),
            )
        else:
            cur.execute(
                """
                INSERT INTO processed_documents
                    (tenant_id, file_hash, file_name, file_size_bytes, mime_type, file_content, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'processing')
                RETURNING id
                """,
                (tenant_id, file_hash, file.filename, len(file_bytes), mime_type, file_bytes),
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

    # ── 3. Fire background processing — return immediately ─────────────────
    asyncio.create_task(
        _process_document_background(doc_id, tenant_id, file_bytes, mime_type, file.filename or "document")
    )

    log.info("action=document_queued tenant=%s doc_id=%s", tenant_id, doc_id)

    return ok_response("Document queued for processing", {
        "status": "processing",
        "doc_id": doc_id,
        "message": "დოკუმენტი მუშავდება ფონზე — approval queue-ში გამოჩნდება რამდენიმე წამში",
    })


async def _process_document_background(
    doc_id: int, tenant_id: str, file_bytes: bytes, mime_type: str, filename: str
):
    """
    Background task: OCR → AI extract → party resolve → classify → draft.
    Runs after upload_document returns. Updates processed_documents.status on finish.
    """
    try:
        llm_service = None
        try:
            from app.api.services.llm_service import llm_service as _llm
            llm_service = _llm
        except Exception:
            pass

        parsed = await parse_document(file_bytes, mime_type, llm_service)
        extracted = await extract_document(parsed.get("text", ""), llm_service)

        # update raw_text + extraction_method
        conn = get_db(tenant_id)
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE processed_documents SET raw_text=%s, extraction_method=%s WHERE id=%s",
                ((parsed.get("text") or "")[:10000], parsed.get("method"), doc_id),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

        # Dedup by doc series+number
        if extracted.document_series and extracted.document_number:
            conn = get_db(tenant_id)
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM journal_drafts WHERE tenant_id=%s AND document_series=%s "
                "AND document_number=%s AND status!='rejected' LIMIT 1",
                (tenant_id, extracted.document_series, extracted.document_number),
            )
            dup = cur.fetchone()
            cur.close()
            conn.close()
            if dup:
                _mark_doc_status(doc_id, "duplicate", tenant_id)
                return

        party = resolve_party(extracted, tenant_id)

        if party.our_role == OurRole.FOREIGN:
            seller_name = extracted.seller.name or extracted.seller.inn or "უცნობი გამყიდველი"
            buyer_name  = extracted.buyer.name  or extracted.buyer.inn  or "უცნობი მყიდველი"
            doc_num     = extracted.document_number or extracted.document_series or ""
            description = f"ინვოისი {doc_num} | {seller_name} → {buyer_name}".strip(" |")
            warning_note = " | ".join(party.warnings) if party.warnings else "გადაამოწმე: შეიძლება სხვა კომპანიის დოკუმენტია"

            conn = get_db(tenant_id)
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO journal_drafts
                        (tenant_id, status, is_foreign_doc, our_role,
                         counterparty_inn, counterparty_name,
                         document_series, document_number, date,
                         amount, description, partner, reason,
                         debit_account, credit_account,
                         raw_extraction, source_document_id, journal_entries)
                    VALUES (%s,'pending_human_review',TRUE,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        tenant_id, party.our_role.value,
                        extracted.seller.inn, extracted.seller.name,
                        extracted.document_series, extracted.document_number,
                        extracted.issue_date, extracted.total_with_vat,
                        description, seller_name, warning_note,
                        None, None,
                        json.dumps(extracted.dict()), doc_id, json.dumps([]),
                    ),
                )
                conn.commit()
            finally:
                cur.close()
                conn.close()
            _mark_doc_status(doc_id, "completed", tenant_id)
            return

        category, cat_confidence = await classify_operation_async(extracted, llm_service)
        is_vat_payer = _get_tenant_vat(tenant_id)
        journal = build_journal(extracted, party, category, is_vat_payer)
        confidence = _confidence_score(parsed, extracted, party, cat_confidence)

        # Extract primary debit/credit accounts from journal entries
        _dr = next((e["dr"] for e in journal["entries"] if "dr" in e), None)
        _cr = next((e["cr"] for e in journal["entries"] if "cr" in e), None)
        _partner = _build_partner(extracted, party)

        conn = get_db(tenant_id)
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO journal_drafts
                    (tenant_id, status, our_role, operation_type, operation_category,
                     counterparty_inn, counterparty_name,
                     document_series, document_number, date,
                     amount, journal_entries, raw_extraction,
                     source_document_id, description, confidence,
                     debit_account, credit_account, partner)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    tenant_id, "pending_approval",
                    party.our_role.value, extracted.document_type, category.value,
                    party.counterparty_inn, party.counterparty_name,
                    extracted.document_series, extracted.document_number,
                    extracted.issue_date, extracted.total_with_vat,
                    json.dumps(journal["entries"]),
                    json.dumps(extracted.dict()),
                    doc_id,
                    _build_description(extracted, party),
                    confidence,
                    _dr, _cr, _partner,
                ),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

        _apply_completeness(tenant_id, doc_id, extracted)

        _upsert_counterparty(
            tenant_id,
            party.counterparty_inn or "",
            party.counterparty_name or "",
            "vendor" if party.our_role == OurRole.BUYER else "customer",
        )

        _mark_doc_status(doc_id, "completed", tenant_id)
        log.info("action=bg_processing_done tenant=%s doc_id=%s role=%s conf=%.2f",
                 tenant_id, doc_id, party.our_role.value, confidence)

    except Exception as e:
        log.error("action=bg_processing_failed doc_id=%s error=%s", doc_id, e)
        _mark_doc_status(doc_id, "failed", tenant_id)


def _apply_completeness(tenant_id: str, source_doc_id: int, extracted: "ExtractedDocument"):
    """
    Build pipeline_docs from the current doc + related waybills/tax_invoices/commercial_invoices,
    run check_document_set, detect provider_type, and UPDATE the matching journal_draft.
    Non-fatal — any failure is logged and swallowed.
    """
    try:
        current = {
            "doc_type": extracted.document_type,
            "doc_number": extracted.document_number or "",
            "total_amount": float(extracted.total_with_vat or 0),
            "seller_inn": extracted.seller.inn,
            "buyer_inn": extracted.buyer.inn,
            "issue_date": extracted.issue_date,
        }
        pipeline_docs = [current]

        seller_inn = extracted.seller.inn
        buyer_inn  = extracted.buyer.inn

        if seller_inn and buyer_inn:
            conn = get_db(tenant_id)
            cur  = conn.cursor()
            try:
                # Related waybill
                cur.execute(
                    "SELECT waybill_number, total_amount, seller_inn, buyer_inn "
                    "FROM waybills WHERE tenant_id=%s AND seller_inn=%s AND buyer_inn=%s "
                    "ORDER BY created_at DESC LIMIT 1",
                    (tenant_id, seller_inn, buyer_inn),
                )
                wb = cur.fetchone()
                if wb:
                    pipeline_docs.append({"doc_type": "waybill", "doc_number": wb[0] or "",
                                          "total_amount": float(wb[1] or 0),
                                          "seller_inn": wb[2], "buyer_inn": wb[3]})
                # Related tax invoice
                cur.execute(
                    "SELECT invoice_number, total_amount, seller_inn, buyer_inn "
                    "FROM tax_invoices WHERE tenant_id=%s AND seller_inn=%s AND buyer_inn=%s "
                    "ORDER BY created_at DESC LIMIT 1",
                    (tenant_id, seller_inn, buyer_inn),
                )
                ti = cur.fetchone()
                if ti:
                    pipeline_docs.append({"doc_type": "tax_invoice", "doc_number": ti[0] or "",
                                          "total_amount": float(ti[1] or 0),
                                          "seller_inn": ti[2], "buyer_inn": ti[3]})
                # Related commercial invoice
                cur.execute(
                    "SELECT invoice_number, total_amount, seller_inn, buyer_inn "
                    "FROM commercial_invoices WHERE tenant_id=%s AND seller_inn=%s AND buyer_inn=%s "
                    "ORDER BY created_at DESC LIMIT 1",
                    (tenant_id, seller_inn, buyer_inn),
                )
                ci = cur.fetchone()
                if ci:
                    pipeline_docs.append({"doc_type": "invoice", "doc_number": ci[0] or "",
                                          "total_amount": float(ci[1] or 0),
                                          "seller_inn": ci[2], "buyer_inn": ci[3]})
            finally:
                cur.close()
                conn.close()

        completeness = check_document_set(pipeline_docs, flow="auto")
        provider_type = classify_provider_type(
            extracted.seller.name, extracted.seller.inn
        ).value

        conn = get_db(tenant_id)
        cur  = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE journal_drafts
                SET doc_set_score       = %s,
                    doc_set_summary     = %s,
                    doc_matrix          = %s,
                    completeness_alerts = %s,
                    provider_type       = %s
                WHERE source_document_id = %s AND tenant_id = %s
                """,
                (
                    completeness.get("score"),
                    completeness.get("summary"),
                    json.dumps(completeness.get("indicators", {})),
                    json.dumps(completeness.get("alerts", [])),
                    provider_type,
                    source_doc_id,
                    tenant_id,
                ),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

        log.info("action=completeness_applied tenant=%s doc_id=%s score=%.2f summary=%s",
                 tenant_id, source_doc_id,
                 completeness.get("score", 0), completeness.get("summary", ""))
    except Exception as e:
        log.warning("action=completeness_failed doc_id=%s: %s", source_doc_id, e)


def _refresh_related_drafts(tenant_id: str, seller_inn: str | None, buyer_inn: str | None):
    """
    When a waybill / tax_invoice / commercial_invoice is added via specialized upload,
    find recent journal_drafts from the same counterparty and update their doc_matrix
    to reflect the newly available document.
    """
    inn = seller_inn or buyer_inn
    if not inn:
        return
    try:
        # 1. Find related drafts
        conn = get_db(tenant_id)
        cur  = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id FROM journal_drafts
                WHERE tenant_id = %s AND counterparty_inn = %s
                  AND status NOT IN ('rejected', 'posted')
                ORDER BY created_at DESC LIMIT 10
                """,
                (tenant_id, inn),
            )
            draft_ids = [r[0] for r in cur.fetchall()]
        finally:
            cur.close()
            conn.close()

        if not draft_ids:
            return

        # 2. Build current doc set from triangle tables
        pipeline_docs = []
        conn = get_db(tenant_id)
        cur  = conn.cursor()
        try:
            cur.execute(
                "SELECT waybill_number, total_amount FROM waybills "
                "WHERE tenant_id=%s AND (seller_inn=%s OR buyer_inn=%s) "
                "ORDER BY created_at DESC LIMIT 1",
                (tenant_id, inn, inn),
            )
            wb = cur.fetchone()
            if wb:
                pipeline_docs.append({"doc_type": "waybill",
                                       "doc_number": wb[0] or "",
                                       "total_amount": float(wb[1] or 0)})

            cur.execute(
                "SELECT invoice_number, total_amount FROM tax_invoices "
                "WHERE tenant_id=%s AND (seller_inn=%s OR buyer_inn=%s) "
                "ORDER BY created_at DESC LIMIT 1",
                (tenant_id, inn, inn),
            )
            ti = cur.fetchone()
            if ti:
                pipeline_docs.append({"doc_type": "tax_invoice",
                                       "doc_number": ti[0] or "",
                                       "total_amount": float(ti[1] or 0)})

            cur.execute(
                "SELECT invoice_number, total_amount FROM commercial_invoices "
                "WHERE tenant_id=%s AND (seller_inn=%s OR buyer_inn=%s) "
                "ORDER BY created_at DESC LIMIT 1",
                (tenant_id, inn, inn),
            )
            ci = cur.fetchone()
            if ci:
                pipeline_docs.append({"doc_type": "invoice",
                                       "doc_number": ci[0] or "",
                                       "total_amount": float(ci[1] or 0)})
        finally:
            cur.close()
            conn.close()

        if not pipeline_docs:
            return

        completeness = check_document_set(pipeline_docs, flow="auto")

        # 3. Bulk-update all matched drafts
        conn = get_db(tenant_id)
        cur  = conn.cursor()
        try:
            cur.executemany(
                """
                UPDATE journal_drafts
                SET doc_set_score       = %s,
                    doc_set_summary     = %s,
                    doc_matrix          = %s,
                    completeness_alerts = %s
                WHERE id = %s AND tenant_id = %s
                """,
                [
                    (
                        completeness.get("score"),
                        completeness.get("summary"),
                        json.dumps(completeness.get("indicators", {})),
                        json.dumps(completeness.get("alerts", [])),
                        did,
                        tenant_id,
                    )
                    for did in draft_ids
                ],
            )
            conn.commit()
            log.info("action=completeness_refreshed tenant=%s drafts=%s inn=%s score=%.2f",
                     tenant_id, draft_ids, inn, completeness.get("score", 0))
        finally:
            cur.close()
            conn.close()

    except Exception as e:
        log.warning("action=refresh_related_drafts_failed inn=%s: %s", inn, e)


def _mark_doc_status(doc_id: int, status: str, tenant_id: str):
    try:
        conn = get_db(tenant_id)
        cur = conn.cursor()
        cur.execute("UPDATE processed_documents SET status=%s WHERE id=%s", (status, doc_id))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.warning("_mark_doc_status failed: %s", e)


# ═══════════════════════════════════════════════════════════════════════════════
# Triangle document upload helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _dec_or_none(val):
    try:
        return float(Decimal(str(val))) if val is not None else None
    except (InvalidOperation, TypeError):
        return None


def _parse_date(val) -> str | None:
    if not val:
        return None
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


async def _extract_from_file(file_bytes: bytes, mime_type: str) -> tuple[dict, ExtractedDocument]:
    """Parse file and extract structured data."""
    try:
        from app.api.services.llm_service import llm_service as _llm
        llm_service = _llm
    except Exception:
        llm_service = None
    parsed = await parse_document(file_bytes, mime_type, llm_service)
    extracted = await extract_document(parsed.get("text", ""), llm_service)
    return parsed, extracted


def _try_match_triangle(conn, tenant_id: str, doc_type: str, doc_id: int, doc: dict):
    """After inserting a doc, find candidates and create/update triangle match."""
    try:
        candidates = find_candidates(conn, tenant_id, doc_type, doc)
        if not candidates:
            return None

        best = candidates[0]
        match_data = {"waybill_id": None, "tax_invoice_id": None, "commercial_invoice_id": None}
        match_data[f"{doc_type}_id"] = doc_id
        match_data[f"{best['doc_type']}_id"] = best["id"]

        wb = None
        ti = None
        ci = None
        if doc_type == "waybill":
            wb = doc
        elif doc_type == "tax_invoice":
            ti = doc
        elif doc_type == "commercial_invoice":
            ci = doc

        if best["doc_type"] == "waybill":
            wb = best
        elif best["doc_type"] == "tax_invoice":
            ti = best
        elif best["doc_type"] == "commercial_invoice":
            ci = best

        result = compute_match_score(wb, ti, ci)
        match_data.update({
            "match_score": result["score"],
            "match_status": result["status"],
            "mismatch_fields": result["mismatches"],
            "waybill_total": _dec_or_none((wb or {}).get("total_amount")),
            "tax_invoice_total": _dec_or_none((ti or {}).get("total_amount")),
            "commercial_invoice_total": _dec_or_none((ci or {}).get("total_amount")),
            "amount_diff": None,
        })

        match_id = upsert_triangle_match(conn, tenant_id, match_data)
        return {"match_id": match_id, "score": result["score"], "status": result["status"]}
    except Exception as e:
        log.warning("triangle match failed: %s", e)
        return None


def _also_queue_for_pipeline(tenant_id: str, file_bytes: bytes, mime_type: str, filename: str):
    """After a specialized upload, also insert into processed_documents and fire the full pipeline
    so a journal draft is created and appears in the approval queue."""
    try:
        import hashlib as _hl
        file_hash = _hl.sha256(file_bytes).hexdigest()  # consistent with main upload
        conn = get_db(tenant_id)
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO processed_documents
                    (tenant_id, file_hash, file_name, file_size_bytes, mime_type, file_content, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'processing')
                ON CONFLICT (tenant_id, file_hash) DO UPDATE
                    SET status = 'processing', file_name = EXCLUDED.file_name
                RETURNING id
                """,
                (tenant_id, file_hash, filename, len(file_bytes), mime_type, file_bytes),
            )
            row = cur.fetchone()
            conn.commit()
        finally:
            cur.close()
            conn.close()

        if row:
            doc_id = row[0]
            asyncio.create_task(
                _process_document_background(doc_id, tenant_id, file_bytes, mime_type, filename)
            )
            log.info("action=specialized_queued_for_pipeline tenant=%s doc_id=%s", tenant_id, doc_id)
    except Exception as e:
        log.warning("_also_queue_for_pipeline failed (non-fatal): %s", e)


# ── Upload Waybill ────────────────────────────────────────────────────────────

@router.post("/upload-waybill")
@limiter.limit("20/minute")
async def upload_waybill(file: UploadFile = File(...), request: Request = None):
    """Upload a waybill (ზედნადები). Extracts fields + attempts triangle match."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None) if request else None)

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        return http_error(413, "File too large (max 10MB)", "FILE_TOO_LARGE")

    mime_type = file.content_type or "application/pdf"
    parsed, extracted = await _extract_from_file(file_bytes, mime_type)

    doc = {
        "waybill_number": extracted.document_number or "",
        "waybill_date": _parse_date(extracted.issue_date),
        "seller_inn": extracted.seller.inn,
        "seller_name": extracted.seller.name,
        "buyer_inn": extracted.buyer.inn,
        "buyer_name": extracted.buyer.name,
        "subtotal": _dec_or_none(extracted.net_amount),
        "vat_amount": _dec_or_none(extracted.total_vat),
        "total_amount": _dec_or_none(extracted.total_with_vat),
        "raw_text": (parsed.get("text") or "")[:5000],
    }

    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO waybills
                (tenant_id, waybill_number, waybill_date, seller_inn, seller_name,
                 buyer_inn, buyer_name, subtotal, vat_amount, total_amount,
                 status, raw_text, version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'imported',%s,1)
            RETURNING id
            """,
            (
                tenant_id, doc["waybill_number"], doc["waybill_date"],
                doc["seller_inn"], doc["seller_name"],
                doc["buyer_inn"], doc["buyer_name"],
                doc["subtotal"], doc["vat_amount"], doc["total_amount"],
                doc["raw_text"],
            ),
        )
        waybill_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return error_response("DB error saving waybill", "DB_ERROR", str(e))
    finally:
        cur.close()

    match_info = _try_match_triangle(conn, tenant_id, "waybill", waybill_id, doc)
    conn.close()

    _refresh_related_drafts(tenant_id, doc.get("seller_inn"), doc.get("buyer_inn"))
    _also_queue_for_pipeline(tenant_id, file_bytes, mime_type, file.filename or "waybill.pdf")

    log.info("action=waybill_uploaded tenant=%s id=%s num=%s",
             tenant_id, waybill_id, doc["waybill_number"])

    return ok_response("Waybill uploaded", {
        "waybill_id": waybill_id,
        "waybill_number": doc["waybill_number"],
        "extracted": extracted.dict(),
        "triangle_match": match_info,
        "extraction_method": parsed.get("method"),
    })


# ── Upload Tax Invoice ────────────────────────────────────────────────────────

@router.post("/upload-tax-invoice")
@limiter.limit("20/minute")
async def upload_tax_invoice(file: UploadFile = File(...), request: Request = None):
    """Upload a tax invoice (საგადასახადო ანგარიშ-ფაქტურა)."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None) if request else None)

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        return http_error(413, "File too large (max 10MB)", "FILE_TOO_LARGE")

    mime_type = file.content_type or "application/pdf"
    parsed, extracted = await _extract_from_file(file_bytes, mime_type)

    doc = {
        "invoice_number": extracted.document_number or "",
        "invoice_series": extracted.document_series or "",
        "invoice_date": _parse_date(extracted.issue_date),
        "seller_inn": extracted.seller.inn,
        "seller_name": extracted.seller.name,
        "buyer_inn": extracted.buyer.inn,
        "buyer_name": extracted.buyer.name,
        "subtotal": _dec_or_none(extracted.net_amount),
        "vat_amount": _dec_or_none(extracted.total_vat),
        "total_amount": _dec_or_none(extracted.total_with_vat),
        "raw_text": (parsed.get("text") or "")[:5000],
    }

    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO tax_invoices
                (tenant_id, invoice_number, invoice_series, invoice_date,
                 seller_inn, seller_name, buyer_inn, buyer_name,
                 subtotal, vat_amount, total_amount, status, raw_text)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'imported',%s)
            RETURNING id
            """,
            (
                tenant_id, doc["invoice_number"], doc["invoice_series"], doc["invoice_date"],
                doc["seller_inn"], doc["seller_name"],
                doc["buyer_inn"], doc["buyer_name"],
                doc["subtotal"], doc["vat_amount"], doc["total_amount"],
                doc["raw_text"],
            ),
        )
        ti_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return error_response("DB error saving tax invoice", "DB_ERROR", str(e))
    finally:
        cur.close()

    match_info = _try_match_triangle(conn, tenant_id, "tax_invoice", ti_id, doc)
    conn.close()

    _refresh_related_drafts(tenant_id, doc.get("seller_inn"), doc.get("buyer_inn"))
    _also_queue_for_pipeline(tenant_id, file_bytes, mime_type, file.filename or "tax_invoice.pdf")

    log.info("action=tax_invoice_uploaded tenant=%s id=%s num=%s",
             tenant_id, ti_id, doc["invoice_number"])

    return ok_response("Tax invoice uploaded", {
        "tax_invoice_id": ti_id,
        "invoice_number": doc["invoice_number"],
        "extracted": extracted.dict(),
        "triangle_match": match_info,
        "extraction_method": parsed.get("method"),
    })


# ── Upload Commercial Invoice ─────────────────────────────────────────────────

@router.post("/upload-commercial-invoice")
@limiter.limit("20/minute")
async def upload_commercial_invoice(file: UploadFile = File(...), request: Request = None):
    """Upload a commercial invoice (ანგარიში)."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None) if request else None)

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        return http_error(413, "File too large (max 10MB)", "FILE_TOO_LARGE")

    mime_type = file.content_type or "application/pdf"
    parsed, extracted = await _extract_from_file(file_bytes, mime_type)

    doc = {
        "invoice_number": extracted.document_number or "",
        "invoice_date": _parse_date(extracted.issue_date),
        "seller_inn": extracted.seller.inn,
        "seller_name": extracted.seller.name,
        "buyer_inn": extracted.buyer.inn,
        "buyer_name": extracted.buyer.name,
        "subtotal": _dec_or_none(extracted.net_amount),
        "vat_amount": _dec_or_none(extracted.total_vat),
        "total_amount": _dec_or_none(extracted.total_with_vat),
        "raw_text": (parsed.get("text") or "")[:5000],
    }

    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO commercial_invoices
                (tenant_id, invoice_number, invoice_date,
                 seller_inn, seller_name, buyer_inn, buyer_name,
                 subtotal, vat_amount, total_amount, status, raw_text)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'imported',%s)
            RETURNING id
            """,
            (
                tenant_id, doc["invoice_number"], doc["invoice_date"],
                doc["seller_inn"], doc["seller_name"],
                doc["buyer_inn"], doc["buyer_name"],
                doc["subtotal"], doc["vat_amount"], doc["total_amount"],
                doc["raw_text"],
            ),
        )
        ci_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return error_response("DB error saving commercial invoice", "DB_ERROR", str(e))
    finally:
        cur.close()

    match_info = _try_match_triangle(conn, tenant_id, "commercial_invoice", ci_id, doc)
    conn.close()

    _refresh_related_drafts(tenant_id, doc.get("seller_inn"), doc.get("buyer_inn"))
    _also_queue_for_pipeline(tenant_id, file_bytes, mime_type, file.filename or "commercial_invoice.pdf")

    log.info("action=commercial_invoice_uploaded tenant=%s id=%s num=%s",
             tenant_id, ci_id, doc["invoice_number"])

    return ok_response("Commercial invoice uploaded", {
        "commercial_invoice_id": ci_id,
        "invoice_number": doc["invoice_number"],
        "extracted": extracted.dict(),
        "triangle_match": match_info,
        "extraction_method": parsed.get("method"),
    })


# ── Triangle match status ─────────────────────────────────────────────────────

@router.get("/triangle-matches")
def list_triangle_matches(
    request: Request,
    status: str = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List triangle matches for tenant, optionally filtered by match_status."""
    import psycopg2.extras
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db(tenant_id)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        where = "WHERE tenant_id = %s"
        params = [tenant_id]
        if status:
            where += " AND match_status = %s"
            params.append(status)
        cur.execute(
            f"""
            SELECT id, waybill_id, tax_invoice_id, commercial_invoice_id,
                   match_score, match_status, mismatch_fields,
                   waybill_total, tax_invoice_total, commercial_invoice_total,
                   amount_diff, matched_at
            FROM triangle_matches {where}
            ORDER BY matched_at DESC LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM triangle_matches {where}", params)
        total = cur.fetchone()["count"]
    finally:
        cur.close()
        conn.close()

    return ok_response("Triangle matches", {
        "total": total, "limit": limit, "offset": offset, "items": rows
    })


# ── Waybills list ─────────────────────────────────────────────────────────────

@router.get("/waybills")
def list_waybills(
    request: Request,
    q: str = Query(None),
    status: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List waybills with triangle-match status joined."""
    import psycopg2.extras
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db(tenant_id)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        conditions = ["w.tenant_id = %s"]
        params: list = [tenant_id]
        if status:
            conditions.append("w.status = %s")
            params.append(status)
        if q:
            conditions.append(
                "(w.waybill_number ILIKE %s OR w.seller_inn ILIKE %s"
                " OR w.buyer_inn ILIKE %s OR w.seller_name ILIKE %s OR w.buyer_name ILIKE %s)"
            )
            like = f"%{q}%"
            params += [like, like, like, like, like]
        where = "WHERE " + " AND ".join(conditions)
        cur.execute(
            f"""
            SELECT w.id, w.waybill_number, w.seller_inn, w.seller_name,
                   w.buyer_inn, w.buyer_name, w.waybill_date,
                   w.subtotal, w.vat_amount, w.total_amount,
                   w.transport_from, w.transport_to,
                   w.status, w.version, w.original_waybill_id, w.notes,
                   w.created_at,
                   tm.match_status, tm.match_score,
                   tm.tax_invoice_id, tm.commercial_invoice_id, tm.id AS match_id
            FROM waybills w
            LEFT JOIN triangle_matches tm
              ON tm.waybill_id = w.id AND tm.tenant_id = w.tenant_id
            {where}
            ORDER BY w.created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM waybills w {where}", params)
        total = cur.fetchone()["count"]
    finally:
        cur.close()
        conn.close()

    return ok_response("Waybills", {"total": total, "limit": limit, "offset": offset, "items": rows})


# ── Tax invoices list ─────────────────────────────────────────────────────────

@router.get("/tax-invoices")
def list_tax_invoices(
    request: Request,
    q: str = Query(None),
    status: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List tax invoices with optional waybill link status."""
    import psycopg2.extras
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db(tenant_id)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        conditions = ["ti.tenant_id = %s"]
        params: list = [tenant_id]
        if status:
            conditions.append("ti.status = %s")
            params.append(status)
        if q:
            conditions.append(
                "(ti.invoice_number ILIKE %s OR ti.seller_inn ILIKE %s"
                " OR ti.buyer_inn ILIKE %s OR ti.seller_name ILIKE %s OR ti.buyer_name ILIKE %s)"
            )
            like = f"%{q}%"
            params += [like, like, like, like, like]
        where = "WHERE " + " AND ".join(conditions)
        cur.execute(
            f"""
            SELECT ti.id, ti.invoice_number, ti.seller_inn, ti.seller_name,
                   ti.buyer_inn, ti.buyer_name, ti.invoice_date,
                   ti.subtotal, ti.vat_amount, ti.total_amount,
                   ti.related_waybill_number, ti.related_waybill_id,
                   ti.status, ti.notes, ti.created_at,
                   tm.match_status, tm.match_score, tm.id AS match_id
            FROM tax_invoices ti
            LEFT JOIN triangle_matches tm
              ON tm.tax_invoice_id = ti.id AND tm.tenant_id = ti.tenant_id
            {where}
            ORDER BY ti.created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM tax_invoices ti {where}", params)
        total = cur.fetchone()["count"]
    finally:
        cur.close()
        conn.close()

    return ok_response("Tax invoices", {"total": total, "limit": limit, "offset": offset, "items": rows})


# ─────────────────────────────────────────────────────────────
# Tax invoice email sending
# ─────────────────────────────────────────────────────────────

from pydantic import BaseModel as _BaseModel, EmailStr as _EmailStr

class _TIEmailReq(_BaseModel):
    email: str

@router.post("/tax-invoice/{invoice_id}/send-email")
@limiter.limit("10/minute")
def send_tax_invoice_email(invoice_id: int, data: _TIEmailReq, request: Request):
    """Generate a PDF for a tax invoice and email it."""
    import io, os, smtplib, json as _json
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email.mime.text import MIMEText
    from email import encoders
    import psycopg2.extras

    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        return error_response("Email not configured", "SMTP_ERROR", "SMTP_USER / SMTP_PASS env vars missing")

    recipient = (data.email or "").strip()
    if not recipient or "@" not in recipient:
        return error_response("Invalid email", "VALIDATION_ERROR", "სწორი ელ-ფოსტა შეიყვანეთ")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db(tenant_id)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM tax_invoices WHERE id = %s AND tenant_id = %s",
            (invoice_id, tenant_id),
        )
        inv = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not inv:
        return http_error(404, "Not found", "NOT_FOUND")
    inv = dict(inv)

    # ── Build PDF ─────────────────────────────────────────────
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
    except ImportError:
        return error_response("reportlab not installed", "PDF_ERROR")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, h - 55, f"Tax Invoice {inv.get('invoice_number') or '#' + str(invoice_id)}")
    c.setFont("Helvetica", 11)
    c.drawString(50, h - 80, f"Date: {str(inv.get('invoice_date') or inv.get('created_at') or '')[:10]}")
    c.drawString(50, h - 98, f"Seller:  {inv.get('seller_name') or '—'}  (INN: {inv.get('seller_inn') or '—'})")
    c.drawString(50, h - 116, f"Buyer:   {inv.get('buyer_name') or '—'}  (INN: {inv.get('buyer_inn') or '—'})")
    y = h - 150
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Subtotal:"); c.drawString(200, y, f"{float(inv.get('subtotal') or 0):.2f} GEL")
    y -= 16
    c.drawString(50, y, "VAT (18%):"); c.drawString(200, y, f"{float(inv.get('vat_amount') or 0):.2f} GEL")
    y -= 16
    c.drawString(50, y, "TOTAL:"); c.drawString(200, y, f"{float(inv.get('total_amount') or 0):.2f} GEL")
    if inv.get("related_waybill_number"):
        y -= 20
        c.setFont("Helvetica", 9)
        c.drawString(50, y, f"Waybill: {inv['related_waybill_number']}")
    if inv.get("notes"):
        y -= 16
        c.setFont("Helvetica", 9)
        c.drawString(50, y, f"Notes: {str(inv['notes'])[:100]}")
    c.save()
    buf.seek(0)
    pdf_bytes = buf.read()

    # ── Send email ────────────────────────────────────────────
    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = recipient
        inv_num = inv.get("invoice_number") or f"#{invoice_id}"
        msg["Subject"] = f"Tax Invoice {inv_num}"
        body = (
            f"Please find the attached tax invoice {inv_num}.\n"
            f"Total: {float(inv.get('total_amount') or 0):.2f} GEL\n\n"
            f"Bridge Hub"
        )
        msg.attach(MIMEText(body, "plain", "utf-8"))
        part = MIMEBase("application", "pdf")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="tax_invoice_{inv_num}.pdf"')
        msg.attach(part)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, recipient, msg.as_string())
    except Exception as e:
        log.error("send_tax_invoice_email failed: %s", e)
        return error_response("Email send failed", "SMTP_ERROR", str(e))

    log.info("action=tax_invoice_emailed tenant=%s id=%s to=%s", tenant_id, invoice_id, recipient)
    return ok_response("ინვოისი გაიგზავნა", {"sent_to": recipient, "invoice_number": inv_num})


# ─────────────────────────────────────────────────────────────
# Original file preview endpoint
# ─────────────────────────────────────────────────────────────

@router.get("/{doc_id}")
async def get_document_meta(doc_id: int, request: Request = None):
    """Return extracted metadata for a processed document (no file bytes)."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None) if request else None)
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT id, file_name, mime_type, file_size_bytes, extraction_method,
                      raw_text, extracted_data, created_at
               FROM processed_documents WHERE id = %s AND tenant_id = %s""",
            (doc_id, tenant_id),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row:
        return http_error(404, "Document not found", "NOT_FOUND")

    import json as _json
    doc_id_val, file_name, mime_type, file_size, method, raw_text, extracted_data, created_at = row
    extracted = {}
    if extracted_data:
        try:
            extracted = _json.loads(extracted_data) if isinstance(extracted_data, str) else extracted_data
        except Exception:
            extracted = {}

    return {
        "ok": True,
        "id": doc_id_val,
        "file_name": file_name,
        "mime_type": mime_type,
        "file_size_bytes": file_size,
        "extraction_method": method,
        "extracted": extracted,
        "created_at": str(created_at) if created_at else None,
    }


@router.get("/{doc_id}/file")
async def get_document_file(doc_id: int, request: Request = None):
    """Serve the original uploaded file bytes for invoice/document preview."""
    from fastapi.responses import Response
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None) if request else None)
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT file_name, mime_type, gcs_path, file_content FROM processed_documents "
            "WHERE id = %s AND tenant_id = %s",
            (doc_id, tenant_id),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row:
        return http_error(404, "Document not found", "NOT_FOUND")

    file_name, mime_type, gcs_path, file_content = row

    content = safe_download(gcs_path, file_content)
    if not content:
        return http_error(404, "File not available — please re-upload", "NOT_FOUND")

    return Response(
        content=content,
        media_type=mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{file_name or "document"}"'},
    )


@router.get("/{doc_id}/url")
async def get_document_signed_url(doc_id: int, request: Request = None):
    """Return a short-lived GCS signed URL for direct browser preview.
    Falls back to {"signed_url": null, "fallback": true} when GCS is unavailable."""
    from app.api.services.storage_service import generate_signed_url
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None) if request else None)
    conn = get_db(tenant_id)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT file_name, mime_type, gcs_path FROM processed_documents "
            "WHERE id = %s AND tenant_id = %s",
            (doc_id, tenant_id),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row:
        return http_error(404, "Document not found", "NOT_FOUND")

    file_name, mime_type, gcs_path = row

    if gcs_path:
        signed_url = generate_signed_url(gcs_path, expires_in=900)
        if signed_url:
            return ok_response({"signed_url": signed_url, "file_name": file_name, "fallback": False})

    # GCS unavailable or no gcs_path — signal client to use /file endpoint
    return ok_response({"signed_url": None, "file_name": file_name, "fallback": True})
