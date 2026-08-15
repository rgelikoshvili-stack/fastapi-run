"""app/api/services/cross_reference_service.py

Sprint 3C — Cross-reference: ties all document types for a given party or document.

For a supplier/buyer (by INN or name):
  waybills → tax invoices → triangle matches → bank payments → journal drafts

For a specific document number:
  find it → find everything linked to it via triangle_matches + amount matching

Read-only. No mutations.
"""
from __future__ import annotations

import logging
from typing import Any

from app.api.db import get_conn, _q

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _safe(row) -> dict:
    if row is None:
        return {}
    import decimal
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, decimal.Decimal):
            d[k] = float(v)
        elif hasattr(v, "isoformat"):
            d[k] = str(v)
    return d


def _payment_status(doc_total: float | None, paid: float) -> str:
    if doc_total is None or doc_total == 0:
        return "unknown"
    if paid >= doc_total * 0.99:
        return "paid"
    if paid > 0:
        return "partial"
    return "unpaid"


# ─────────────────────────────────────────────────────────────────────────────
# Party cross-reference
# ─────────────────────────────────────────────────────────────────────────────

async def get_cross_ref_by_party(
    tenant_id: str,
    query: str,
    limit: int = 20,
) -> dict:
    """
    Return all documents linked to a party (supplier/buyer).
    query: INN number, company name, or partial name.
    """
    query = query.strip()
    if not query:
        return {"error": "query required"}

    like = f"%{query}%"

    async with get_conn() as conn:
        # ── Waybills ────────────────────────────────────────────────────────
        waybills = []
        try:
            rows = await conn.fetch(_q("""
                SELECT w.id, w.waybill_number, w.waybill_date,
                       w.seller_inn, w.seller_name, w.buyer_inn, w.buyer_name,
                       w.total_amount, w.vat_amount, w.status, w.source,
                       tm.match_status, tm.match_score, tm.id AS triangle_id
                FROM waybills w
                LEFT JOIN triangle_matches tm ON tm.waybill_id=w.id AND tm.tenant_id=w.tenant_id
                WHERE w.tenant_id=%s
                  AND (w.seller_inn ILIKE %s OR w.seller_name ILIKE %s
                       OR w.buyer_inn ILIKE %s  OR w.buyer_name ILIKE %s)
                ORDER BY w.waybill_date DESC NULLS LAST
                LIMIT %s
            """), tenant_id, like, like, like, like, limit)
            waybills = [_safe(r) for r in rows]
        except Exception as e:
            log.debug("cross_ref waybills: %s", e)

        # ── Tax invoices ─────────────────────────────────────────────────────
        tax_invoices = []
        try:
            rows = await conn.fetch(_q("""
                SELECT ti.id, ti.invoice_number, ti.invoice_series, ti.invoice_date,
                       ti.seller_inn, ti.seller_name, ti.buyer_inn, ti.buyer_name,
                       ti.total_amount, ti.vat_amount, ti.status,
                       ti.related_waybill_number, ti.source,
                       tm.match_status, tm.match_score, tm.id AS triangle_id
                FROM tax_invoices ti
                LEFT JOIN triangle_matches tm ON tm.tax_invoice_id=ti.id AND tm.tenant_id=ti.tenant_id
                WHERE ti.tenant_id=%s
                  AND (ti.seller_inn ILIKE %s OR ti.seller_name ILIKE %s
                       OR ti.buyer_inn ILIKE %s  OR ti.buyer_name ILIKE %s)
                ORDER BY ti.invoice_date DESC NULLS LAST
                LIMIT %s
            """), tenant_id, like, like, like, like, limit)
            tax_invoices = [_safe(r) for r in rows]
        except Exception as e:
            log.debug("cross_ref tax_invoices: %s", e)

        # ── Bank transactions ────────────────────────────────────────────────
        bank_txns = []
        try:
            rows = await conn.fetch(_q("""
                SELECT bt.id, bt.bank, bt.date, bt.amount, bt.currency,
                       bt.description, bt.partner, bt.operation_code,
                       bt.transaction_ref, bt.balance,
                       br.id IS NOT NULL AS is_reconciled
                FROM bank_transactions bt
                LEFT JOIN bank_reconciliations br
                    ON br.bank_transaction_id::text = bt.id::text
                   AND br.tenant_id = bt.tenant_id
                WHERE bt.tenant_id=%s
                  AND (bt.partner ILIKE %s OR bt.description ILIKE %s)
                ORDER BY bt.date DESC
                LIMIT %s
            """), tenant_id, like, like, limit)
            bank_txns = [_safe(r) for r in rows]
        except Exception as e:
            log.debug("cross_ref bank_txns: %s", e)

        # ── Journal drafts ───────────────────────────────────────────────────
        drafts = []
        try:
            rows = await conn.fetch(_q("""
                SELECT id, description, amount, partner, status, confidence,
                       debit_account, credit_account, date, created_at
                FROM journal_drafts
                WHERE tenant_id=%s
                  AND (partner ILIKE %s OR description ILIKE %s)
                ORDER BY created_at DESC
                LIMIT %s
            """), tenant_id, like, like, limit)
            drafts = [_safe(r) for r in rows]
        except Exception as e:
            log.debug("cross_ref drafts: %s", e)

    # ── Summary ───────────────────────────────────────────────────────────────
    total_invoiced = sum(
        float(w.get("total_amount") or 0) for w in waybills
    )
    total_paid = sum(
        float(b.get("amount") or 0) for b in bank_txns if float(b.get("amount") or 0) > 0
    )
    unmatched_waybills = [w for w in waybills if not w.get("triangle_id")]

    return {
        "query": query,
        "party_type": "INN" if query.isdigit() else "name",
        "waybills": waybills,
        "tax_invoices": tax_invoices,
        "bank_transactions": bank_txns,
        "journal_drafts": drafts,
        "summary": {
            "waybill_count": len(waybills),
            "tax_invoice_count": len(tax_invoices),
            "bank_txn_count": len(bank_txns),
            "draft_count": len(drafts),
            "total_invoiced_gel": total_invoiced,
            "total_paid_gel": total_paid,
            "payment_status": _payment_status(total_invoiced, total_paid),
            "unmatched_waybills": len(unmatched_waybills),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Document cross-reference
# ─────────────────────────────────────────────────────────────────────────────

async def get_cross_ref_by_document(
    tenant_id: str,
    doc_number: str,
) -> dict:
    """
    Return everything linked to a specific document number (waybill or tax invoice).
    """
    doc_number = doc_number.strip()
    if not doc_number:
        return {"error": "doc_number required"}

    like = f"%{doc_number}%"

    async with get_conn() as conn:
        # ── Find the anchor document ──────────────────────────────────────────
        waybill = None
        tax_invoice = None

        try:
            row = await conn.fetchrow(_q("""
                SELECT id, waybill_number, waybill_date, seller_inn, seller_name,
                       buyer_inn, buyer_name, total_amount, vat_amount, status, source
                FROM waybills
                WHERE tenant_id=%s AND waybill_number ILIKE %s
                ORDER BY id DESC LIMIT 1
            """), tenant_id, like)
            if row:
                waybill = _safe(row)
        except Exception as e:
            log.debug("cross_ref_by_doc waybill anchor: %s", e)

        if not waybill:
            try:
                row = await conn.fetchrow(_q("""
                    SELECT id, invoice_number, invoice_series, invoice_date,
                           seller_inn, seller_name, buyer_inn, buyer_name,
                           total_amount, vat_amount, status, source,
                           related_waybill_number
                    FROM tax_invoices
                    WHERE tenant_id=%s AND invoice_number ILIKE %s
                    ORDER BY id DESC LIMIT 1
                """), tenant_id, like)
                if row:
                    tax_invoice = _safe(row)
            except Exception as e:
                log.debug("cross_ref_by_doc tax_invoice anchor: %s", e)

        if not waybill and not tax_invoice:
            return {"found": False, "doc_number": doc_number}

        anchor_doc = waybill or tax_invoice
        anchor_type = "waybill" if waybill else "tax_invoice"
        anchor_id = anchor_doc["id"]
        anchor_total = float(anchor_doc.get("total_amount") or 0)
        seller_inn = anchor_doc.get("seller_inn")
        seller_name = anchor_doc.get("seller_name")
        buyer_inn = anchor_doc.get("buyer_inn")

        # ── Triangle match ────────────────────────────────────────────────────
        triangle = None
        linked_waybill = None
        linked_tax_invoice = None
        try:
            if anchor_type == "waybill":
                tm_row = await conn.fetchrow(_q("""
                    SELECT tm.*,
                           ti.invoice_number, ti.invoice_series, ti.invoice_date,
                           ti.total_amount AS ti_total, ti.status AS ti_status
                    FROM triangle_matches tm
                    LEFT JOIN tax_invoices ti ON ti.id=tm.tax_invoice_id AND ti.tenant_id=tm.tenant_id
                    WHERE tm.tenant_id=%s AND tm.waybill_id=%s
                    ORDER BY tm.match_score DESC LIMIT 1
                """), tenant_id, anchor_id)
                if tm_row:
                    triangle = _safe(tm_row)
                    linked_tax_invoice = {
                        "invoice_number": tm_row["invoice_number"],
                        "invoice_series": tm_row["invoice_series"],
                        "invoice_date": str(tm_row["invoice_date"]) if tm_row["invoice_date"] else None,
                        "total_amount": float(tm_row["ti_total"] or 0) if tm_row["ti_total"] else None,
                        "status": tm_row["ti_status"],
                    } if tm_row["invoice_number"] else None
            else:
                tm_row = await conn.fetchrow(_q("""
                    SELECT tm.*,
                           w.waybill_number, w.waybill_date,
                           w.total_amount AS wb_total, w.status AS wb_status
                    FROM triangle_matches tm
                    LEFT JOIN waybills w ON w.id=tm.waybill_id AND w.tenant_id=tm.tenant_id
                    WHERE tm.tenant_id=%s AND tm.tax_invoice_id=%s
                    ORDER BY tm.match_score DESC LIMIT 1
                """), tenant_id, anchor_id)
                if tm_row:
                    triangle = _safe(tm_row)
                    linked_waybill = {
                        "waybill_number": tm_row["waybill_number"],
                        "waybill_date": str(tm_row["waybill_date"]) if tm_row["waybill_date"] else None,
                        "total_amount": float(tm_row["wb_total"] or 0) if tm_row["wb_total"] else None,
                        "status": tm_row["wb_status"],
                    } if tm_row["waybill_number"] else None
        except Exception as e:
            log.debug("cross_ref_by_doc triangle: %s", e)

        # ── Bank payments (match by amount ± 1 GEL and seller/partner name) ──
        bank_txns = []
        try:
            partner_like = f"%{seller_name}%" if seller_name else "%"
            rows = await conn.fetch(_q("""
                SELECT bt.id, bt.bank, bt.date, bt.amount, bt.currency,
                       bt.description, bt.partner, bt.transaction_ref,
                       br.id IS NOT NULL AS is_reconciled
                FROM bank_transactions bt
                LEFT JOIN bank_reconciliations br
                    ON br.bank_transaction_id::text = bt.id::text
                   AND br.tenant_id = bt.tenant_id
                WHERE bt.tenant_id=%s
                  AND (
                      ABS(ABS(bt.amount) - %s) < 1.0
                      OR (bt.partner ILIKE %s OR bt.description ILIKE %s)
                  )
                ORDER BY bt.date DESC
                LIMIT 10
            """), tenant_id, anchor_total, partner_like, partner_like)
            bank_txns = [_safe(r) for r in rows]
        except Exception as e:
            log.debug("cross_ref_by_doc bank: %s", e)

        # ── Journal draft ─────────────────────────────────────────────────────
        drafts = []
        try:
            rows = await conn.fetch(_q("""
                SELECT id, description, amount, partner, status,
                       debit_account, credit_account, date, confidence
                FROM journal_drafts
                WHERE tenant_id=%s
                  AND (
                      (partner ILIKE %s AND ABS(COALESCE(amount,0) - %s) < 1.0)
                      OR description ILIKE %s
                  )
                ORDER BY created_at DESC LIMIT 5
            """), tenant_id,
                f"%{seller_name}%" if seller_name else "%",
                anchor_total,
                f"%{doc_number}%")
            drafts = [_safe(r) for r in rows]
        except Exception as e:
            log.debug("cross_ref_by_doc drafts: %s", e)

    # ── Infer payment status ──────────────────────────────────────────────────
    paid = sum(
        float(b.get("amount") or 0) for b in bank_txns if float(b.get("amount") or 0) > 0
    )

    chain: dict[str, Any] = {
        "anchor_type": anchor_type,
        "anchor_doc_number": doc_number,
        "anchor": anchor_doc,
    }
    if anchor_type == "waybill":
        chain["linked_tax_invoice"] = linked_tax_invoice
    else:
        chain["linked_waybill"] = linked_waybill
        if waybill:
            chain["waybill"] = waybill

    chain.update({
        "triangle_match": triangle,
        "bank_payments": bank_txns,
        "journal_drafts": drafts,
        "payment_status": _payment_status(anchor_total, paid),
        "paid_amount": paid,
        "invoiced_amount": anchor_total,
        "found": True,
    })
    return chain
