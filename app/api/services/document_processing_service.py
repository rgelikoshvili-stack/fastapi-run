"""
app/api/services/document_processing_service.py

Private helpers for the document upload + intelligence pipeline.
Called exclusively from app/api/routes_documents.py.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.api.db import get_db
from app.api.services.document_parser import parse_document
from app.api.services.document_extractor import extract_document, ExtractedDocument
from app.api.services.party_resolver import resolve_party, OurRole
from app.api.services.operation_classifier import classify_operation_async
from app.api.services.doc_journal_builder import build_journal
from app.api.services.triangle_matcher import compute_match_score, find_candidates, upsert_triangle_match
from app.api.services.completeness_checker import check_document_set
from app.api.services.contract_classifier import classify_provider_type

log = logging.getLogger(__name__)


# ── Confidence scoring ─────────────────────────────────────────────────────────

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


# ── Name extraction ────────────────────────────────────────────────────────────

def _parse_company_from_notes(notes: str) -> str | None:
    """Extract Georgian company name from raw OCR notes — prefers შპს over სს to avoid bank names."""
    if not notes:
        return None
    m = re.search(r'შპს\s+([\w][^\n]{2,60})', notes, re.UNICODE)
    if m:
        name = 'შპს ' + m.group(1).split('\n')[0].strip().rstrip('.,;:')
        name = re.sub(r'\s+(INVOICE|invoice|ინვოისი|შეკვ|ზედნ).*', '', name, flags=re.I).strip()
        if 6 < len(name) < 80:
            return name
    m = re.search(r'ი/მ\s+([\w][^\n]{2,60})', notes, re.UNICODE)
    if m:
        name = 'ი/მ ' + m.group(1).split('\n')[0].strip().rstrip('.,;:')
        if 6 < len(name) < 80:
            return name
    for m in re.finditer(r'სს\s+([\w][^\n]{2,60})', notes, re.UNICODE):
        line = notes[max(0, m.start()-15):m.start()]
        if 'ბანკი' in line or 'bank' in line.lower():
            continue
        name = 'სს ' + m.group(1).split('\n')[0].strip().rstrip('.,;:')
        if 6 < len(name) < 80:
            return name
    return None


def _resolve_seller_name(extracted: ExtractedDocument, party) -> str:
    """Best available counterparty name — falls back to notes parsing."""
    name = (
        party.counterparty_name
        or extracted.seller.name
        or extracted.buyer.name
    )
    if not name:
        name = _parse_company_from_notes(extracted.notes or "")
    return name or ""


def _build_description(extracted: ExtractedDocument, party, draft_id: int = None, amount=None) -> str:
    company = _resolve_seller_name(extracted, party)
    inn = party.counterparty_inn or extracted.seller.inn or getattr(extracted, "seller_inn", "") or ""
    if company and inn:
        return f"{company} ({inn})"
    return company or inn or "?"


def _build_partner(extracted: ExtractedDocument, party) -> str:
    doc_num = extracted.document_number or extracted.document_series
    return f"№{doc_num}" if doc_num else ""


# ── DB helpers ─────────────────────────────────────────────────────────────────

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


def _apply_completeness(tenant_id: str, source_doc_id: int, extracted: ExtractedDocument):
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
    find recent journal_drafts from the same counterparty and update their doc_matrix.
    """
    inn = seller_inn or buyer_inn
    if not inn:
        return
    try:
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


# ── Triangle document helpers ──────────────────────────────────────────────────

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

        wb = ti = ci = None
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
    """After a specialized upload, also insert into processed_documents and fire the full pipeline."""
    try:
        file_hash = hashlib.sha256(file_bytes).hexdigest()
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


# ── Main background pipeline ───────────────────────────────────────────────────

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
        except Exception as e:
            log.warning("unexpected error: %s", e)

        parsed = await parse_document(file_bytes, mime_type, llm_service)
        extracted = await extract_document(parsed.get("text", ""), llm_service)

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
