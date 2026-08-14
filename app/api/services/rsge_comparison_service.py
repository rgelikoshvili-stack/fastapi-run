"""app/api/services/rsge_comparison_service.py — Structured RS.ge document comparison.

Compares RS.ge documents/waybills against Bridge Hub internal state:
  - Evidence (documents table)
  - Journal Drafts (journal_drafts table)
  - Posted Ledger (posted_journal_entries table)
  - Waybill vs Invoice (cross-document)

All comparisons are read-only. No RS.ge mutations. No auto-posting.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

log = logging.getLogger(__name__)

# ── Tolerance ─────────────────────────────────────────────────────────────────
_AMOUNT_TOLERANCE = Decimal("0.02")
_VAT_TOLERANCE    = Decimal("0.05")

# ── Status constants ──────────────────────────────────────────────────────────
MATCHED               = "matched"
AMOUNT_MISMATCH       = "amount_mismatch"
VAT_MISMATCH          = "vat_mismatch"
SELLER_BUYER_MISMATCH = "seller_buyer_mismatch"
LINE_MISMATCH         = "line_mismatch"
PRODUCT_UNMAPPED      = "product_unmapped"
MISSING_IN_BRIDGE     = "missing_in_bridge"
MISSING_IN_RSGE       = "missing_in_rsge"
DUPLICATE             = "duplicate"
REQUIRES_REVIEW       = "requires_review"

# Risk levels
RISK_LOW    = "low"
RISK_MEDIUM = "medium"
RISK_HIGH   = "high"


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except InvalidOperation:
        return Decimal("0")


def _risk(statuses: list[str]) -> str:
    if SELLER_BUYER_MISMATCH in statuses or DUPLICATE in statuses:
        return RISK_HIGH
    if any(s in statuses for s in (AMOUNT_MISMATCH, VAT_MISMATCH, LINE_MISMATCH)):
        return RISK_MEDIUM
    return RISK_LOW


# ── 1. RS.ge document vs Evidence ─────────────────────────────────────────────

async def compare_document_vs_evidence(
    conn, tenant_id: str, rsge_doc_id: int, own_inn: str = "",
) -> dict:
    """Compare a synced RS.ge document against its linked Bridge Hub evidence."""
    from app.api.db import _q
    doc_row = await conn.fetchrow(
        _q("SELECT * FROM rsge_documents WHERE id=%s AND tenant_id=%s"),
        rsge_doc_id, tenant_id,
    )
    if not doc_row:
        return _missing("rsge_document", rsge_doc_id)
    doc = dict(doc_row)

    if not doc.get("evidence_id"):
        return _build(rsge_doc_id, None, "evidence", MISSING_IN_BRIDGE, doc=doc,
                      mismatch="ყ. ევ. შ.")

    ev_row = await conn.fetchrow(
        _q("SELECT * FROM documents WHERE id=%s AND tenant_id=%s"),
        doc["evidence_id"], tenant_id,
    )
    if not ev_row:
        return _build(rsge_doc_id, doc["evidence_id"], "evidence",
                      MISSING_IN_BRIDGE, doc=doc, mismatch="ევ. DB-ში ვ.მ.")

    ev = dict(ev_row)
    issues, mismatches = [], []

    # Amount check
    doc_amt = _dec(doc.get("amount"))
    ev_amt  = _dec(ev.get("amount"))
    amount_status = MATCHED
    if abs(doc_amt - ev_amt) > _AMOUNT_TOLERANCE:
        issues.append(AMOUNT_MISMATCH)
        amount_status = AMOUNT_MISMATCH
        mismatches.append(f"თანხა: RS.ge={doc_amt} ≠ ევ.={ev_amt}")

    # VAT check (if available)
    vat_status = MATCHED
    doc_vat = _dec(doc.get("vat_amount"))
    if doc_vat > 0:
        extracted = {}
        try:
            extracted = json.loads(ev.get("extracted_data") or "{}")
        except Exception:
            pass
        ev_vat = _dec(extracted.get("vat_amount", 0))
        if ev_vat > 0 and abs(doc_vat - ev_vat) > _VAT_TOLERANCE:
            issues.append(VAT_MISMATCH)
            vat_status = VAT_MISMATCH
            mismatches.append(f"დღგ: RS.ge={doc_vat} ≠ ევ.={ev_vat}")

    overall = MATCHED if not issues else issues[0]
    return _build(rsge_doc_id, doc["evidence_id"], "evidence", overall, doc=doc,
                  amount_status=amount_status, vat_status=vat_status,
                  amount_diff=float(abs(doc_amt - ev_amt)),
                  mismatch="; ".join(mismatches) if mismatches else None,
                  risk=_risk(issues))


# ── 2. RS.ge document vs Journal Draft ───────────────────────────────────────

async def compare_document_vs_draft(
    conn, tenant_id: str, rsge_doc_id: int, own_inn: str = "",
) -> dict:
    """Compare synced RS.ge document against its linked accounting draft."""
    from app.api.db import _q
    doc_row = await conn.fetchrow(
        _q("SELECT * FROM rsge_documents WHERE id=%s AND tenant_id=%s"),
        rsge_doc_id, tenant_id,
    )
    if not doc_row:
        return _missing("rsge_document", rsge_doc_id)
    doc = dict(doc_row)

    if not doc.get("draft_id"):
        return _build(rsge_doc_id, None, "journal_draft", MISSING_IN_BRIDGE, doc=doc,
                      mismatch="დ. შ. ვ. ა.")

    draft_row = await conn.fetchrow(
        _q("SELECT * FROM journal_drafts WHERE id=%s AND tenant_id=%s"),
        doc["draft_id"], tenant_id,
    )
    if not draft_row:
        return _build(rsge_doc_id, doc["draft_id"], "journal_draft",
                      MISSING_IN_BRIDGE, doc=doc, mismatch="დ. DB-ში ვ.მ.")

    draft = dict(draft_row)
    issues, mismatches = [], []

    doc_amt   = _dec(doc.get("amount"))
    draft_amt = _dec(draft.get("amount"))
    amount_status = MATCHED
    if abs(doc_amt - draft_amt) > _AMOUNT_TOLERANCE:
        issues.append(AMOUNT_MISMATCH)
        amount_status = AMOUNT_MISMATCH
        mismatches.append(f"თანხა: RS.ge={doc_amt} ≠ დრ.={draft_amt}")

    overall = MATCHED if not issues else issues[0]
    return _build(rsge_doc_id, doc["draft_id"], "journal_draft", overall, doc=doc,
                  amount_status=amount_status,
                  amount_diff=float(abs(doc_amt - draft_amt)),
                  bridge_status=draft.get("status"),
                  mismatch="; ".join(mismatches) if mismatches else None,
                  risk=_risk(issues))


# ── 3. RS.ge document vs Posted Ledger ───────────────────────────────────────

async def compare_document_vs_ledger(
    conn, tenant_id: str, rsge_doc_id: int,
) -> dict:
    """Compare synced RS.ge document against posted ledger entries."""
    from app.api.db import _q
    doc_row = await conn.fetchrow(
        _q("SELECT * FROM rsge_documents WHERE id=%s AND tenant_id=%s"),
        rsge_doc_id, tenant_id,
    )
    if not doc_row:
        return _missing("rsge_document", rsge_doc_id)
    doc = dict(doc_row)

    draft_id = doc.get("draft_id")
    if not draft_id:
        return _build(rsge_doc_id, None, "posted_ledger", MISSING_IN_BRIDGE, doc=doc,
                      mismatch="დ. ვ. ა. — გატ. ვ. შ.")

    # Check if draft was posted
    draft_row = await conn.fetchrow(
        _q("SELECT id, status, amount FROM journal_drafts WHERE id=%s AND tenant_id=%s"),
        draft_id, tenant_id,
    )
    if not draft_row or draft_row["status"] != "posted":
        return _build(rsge_doc_id, draft_id, "posted_ledger", MISSING_IN_BRIDGE, doc=doc,
                      bridge_status=dict(draft_row or {}).get("status"),
                      mismatch="დ. ჯ. გ. ვ. — სტ.: " + (dict(draft_row or {}).get("status") or "unknown"))

    doc_amt   = _dec(doc.get("amount"))
    draft_amt = _dec(draft_row["amount"])
    issues = []
    amount_status = MATCHED
    if abs(doc_amt - draft_amt) > _AMOUNT_TOLERANCE:
        issues.append(AMOUNT_MISMATCH)
        amount_status = AMOUNT_MISMATCH

    overall = MATCHED if not issues else issues[0]
    return _build(rsge_doc_id, draft_id, "posted_ledger", overall, doc=doc,
                  amount_status=amount_status,
                  amount_diff=float(abs(doc_amt - draft_amt)),
                  bridge_status="posted", risk=_risk(issues))


# ── 4. RS.ge waybill vs RS.ge invoice ────────────────────────────────────────

async def compare_waybill_vs_invoice(
    conn, tenant_id: str, waybill_id: int,
) -> dict:
    """Compare a synced waybill against its linked invoice (by waybill_number)."""
    from app.api.db import _q
    import json as _json
    wb_row = await conn.fetchrow(
        _q("SELECT * FROM rsge_waybills WHERE id=%s AND tenant_id=%s"),
        waybill_id, tenant_id,
    )
    if not wb_row:
        return _missing("rsge_waybill", waybill_id)
    wb = dict(wb_row)
    wb_num = wb.get("waybill_number") or ""

    # Find linked invoices in rsge_documents by waybill_number
    inv_rows = await conn.fetch(
        _q("SELECT * FROM rsge_documents WHERE tenant_id=%s AND waybill_number=%s"),
        tenant_id, wb_num,
    ) if wb_num else []

    if not inv_rows:
        return _build(waybill_id, None, "invoice", MISSING_IN_BRIDGE,
                      mismatch="ζεδ. #" + wb_num + " ფ-ებ. ვ.მ.",
                      wb_amount=float(wb.get("full_amount") or 0))

    wb_amt   = _dec(wb.get("full_amount"))
    inv_amt  = sum(_dec(r["amount"]) for r in inv_rows)
    issues   = []
    mismatches = []

    amount_status = MATCHED
    if abs(wb_amt - inv_amt) > _AMOUNT_TOLERANCE:
        issues.append(AMOUNT_MISMATCH)
        amount_status = AMOUNT_MISMATCH
        mismatches.append(f"თ: ζεδ.={wb_amt} ≠ ფ.={inv_amt}")

    # Goods vs lines comparison
    try:
        raw = _json.loads(wb.get("raw_payload") or "{}")
        wb_goods = raw.get("goods_list") or []
    except Exception:
        wb_goods = []

    all_inv_lines = []
    for r in inv_rows:
        try:
            rp = _json.loads(r.get("raw_payload") or "{}")
            all_inv_lines.extend(rp.get("lines") or [])
        except Exception:
            pass

    line_status = MATCHED
    wb_names = {(g.get("name") or "").strip().lower() for g in wb_goods}
    extra_lines = [l for l in all_inv_lines
                   if (l.get("name") or "").strip().lower() not in wb_names]
    if extra_lines:
        mismatches.append(f"დ. ხ.: {len(extra_lines)} ზ. ი. ჰ.")

    overall = MATCHED if not issues else issues[0]
    return _build(waybill_id, inv_rows[0]["id"] if inv_rows else None, "invoice",
                  overall,
                  amount_status=amount_status, line_status=line_status,
                  amount_diff=float(abs(wb_amt - inv_amt)),
                  wb_amount=float(wb_amt), inv_amount=float(inv_amt),
                  diff_lines=extra_lines,
                  line_diff_count=len(extra_lines),
                  mismatch="; ".join(mismatches) if mismatches else None,
                  risk=_risk(issues))


# ── 5. Unmapped product check ────────────────────────────────────────────────

async def check_product_mapping(
    conn, tenant_id: str, goods_list: list,
) -> dict:
    """Check which goods codes are mapped in rsge_item_map."""
    from app.api.db import _q
    if not goods_list:
        return {"status": MATCHED, "unmapped": [], "mapped": []}
    codes = [
        str(g.get("bar_code") or g.get("product_code") or g.get("code") or "").strip()
        for g in goods_list
    ]
    codes = [c for c in codes if c]
    mapped, unmapped = [], []
    for code in codes:
        row = await conn.fetchrow(
            _q("SELECT account_code FROM rsge_item_map WHERE tenant_id=%s AND item_code=%s"),
            tenant_id, code,
        )
        (mapped if row else unmapped).append(code)
    status = PRODUCT_UNMAPPED if unmapped else MATCHED
    return {"status": status, "mapped": mapped, "unmapped": unmapped,
            "risk": RISK_MEDIUM if unmapped else RISK_LOW}


# ── Persist comparison result ─────────────────────────────────────────────────

async def save_comparison_result(conn, tenant_id: str, result: dict,
                                  created_by: str = "") -> int:
    """Persist a comparison result to rsge_comparison_results."""
    from app.api.db import _q
    import json as _json
    try:
        row = await conn.fetchrow(
            _q("""INSERT INTO rsge_comparison_results
                   (tenant_id, waybill_id, document_id, status,
                    wb_amount, inv_amount, diff_amount, diff_lines,
                    notes, reviewed_by)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                 RETURNING id"""),
            tenant_id,
            result.get("waybill_id"), result.get("document_id"),
            result.get("comparison_status", REQUIRES_REVIEW),
            result.get("wb_amount", 0), result.get("inv_amount", 0),
            result.get("amount_diff", 0),
            _json.dumps(result.get("diff_lines") or []),
            result.get("mismatch_summary"), created_by,
        )
        return row["id"] if row else 0
    except Exception as exc:
        log.debug("save_comparison_result failed: %s", exc)
        return 0


# ── Internal builder ─────────────────────────────────────────────────────────

def _build(source_id: int, target_id, target_type: str, status: str,
           doc: dict = None, amount_status=MATCHED, vat_status=MATCHED,
           line_status=MATCHED, amount_diff=0.0, vat_diff=0.0,
           wb_amount=0.0, inv_amount=0.0, diff_lines=None,
           line_diff_count=0, bridge_status=None, mismatch=None,
           risk=RISK_LOW) -> dict:
    doc = doc or {}
    rsge_status = doc.get("rsge_status") or doc.get("rsge_status_code") or ""
    return {
        "comparison_status":       status,
        "document_id":             source_id if target_type != "invoice" else None,
        "waybill_id":              source_id if target_type == "invoice" else None,
        "compare_target_type":     target_type,
        "compare_target_id":       target_id,
        "amount_status":           amount_status,
        "vat_status":              vat_status,
        "line_status":             line_status,
        "rsge_status":             rsge_status,
        "bridge_status":           bridge_status,
        "amount_diff":             round(amount_diff, 4),
        "vat_diff":                round(vat_diff, 4),
        "wb_amount":               round(wb_amount, 4),
        "inv_amount":              round(inv_amount, 4),
        "diff_lines":              diff_lines or [],
        "line_diff_count":         line_diff_count,
        "mismatch_summary":        mismatch,
        "risk_level":              risk,
        "seller_inn":              doc.get("seller_inn") or "",
        "buyer_inn":               doc.get("buyer_inn") or "",
    }


def _missing(entity: str, eid: int) -> dict:
    return {
        "comparison_status": MISSING_IN_BRIDGE,
        "document_id": eid if "document" in entity else None,
        "waybill_id":  eid if "waybill"  in entity else None,
        "compare_target_type": "none",
        "compare_target_id":   None,
        "amount_status": REQUIRES_REVIEW,
        "mismatch_summary": f"{entity} id={eid} not found",
        "risk_level": RISK_HIGH,
    }
