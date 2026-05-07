"""Triangle Reconciliation — links waybill + tax_invoice + commercial_invoice."""
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

log = logging.getLogger(__name__)

_AMOUNT_TOLERANCE = Decimal("0.05")  # 5 tetri tolerance for rounding differences


def _dec(val) -> Optional[Decimal]:
    try:
        return Decimal(str(val)) if val is not None else None
    except (InvalidOperation, TypeError):
        return None


def _amounts_match(a: Optional[Decimal], b: Optional[Decimal]) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= _AMOUNT_TOLERANCE


def _inns_match(inn_a: Optional[str], inn_b: Optional[str]) -> bool:
    if not inn_a or not inn_b:
        return False
    return inn_a.strip() == inn_b.strip()


def compute_match_score(
    waybill: Optional[dict],
    tax_invoice: Optional[dict],
    commercial_invoice: Optional[dict],
) -> dict:
    """Score 0–1 + mismatch_fields list for the three documents."""
    score = 0.0
    mismatches = []
    present = sum(1 for d in [waybill, tax_invoice, commercial_invoice] if d)

    if present == 0:
        return {"score": 0.0, "status": "partial", "mismatches": []}

    # ── Amount checks ────────────────────────────────────────────────────────
    amounts = {}
    if waybill:
        amounts["waybill"] = _dec(waybill.get("total_amount"))
    if tax_invoice:
        amounts["tax_invoice"] = _dec(tax_invoice.get("total_amount"))
    if commercial_invoice:
        amounts["commercial_invoice"] = _dec(commercial_invoice.get("total_amount"))

    vals = [v for v in amounts.values() if v is not None]
    if len(vals) >= 2:
        if all(_amounts_match(vals[0], v) for v in vals[1:]):
            score += 0.40
        else:
            mismatches.append("amount_mismatch")

    # ── INN cross-check ──────────────────────────────────────────────────────
    inns_ok = True
    if waybill and tax_invoice:
        if not _inns_match(waybill.get("seller_inn"), tax_invoice.get("seller_inn")):
            mismatches.append("seller_inn_mismatch")
            inns_ok = False
        if not _inns_match(waybill.get("buyer_inn"), tax_invoice.get("buyer_inn")):
            mismatches.append("buyer_inn_mismatch")
            inns_ok = False
    if inns_ok and (waybill or tax_invoice):
        score += 0.25

    # ── Date proximity (within 5 days) ──────────────────────────────────────
    dates = []
    for doc in [waybill, tax_invoice, commercial_invoice]:
        if doc:
            d = doc.get("waybill_date") or doc.get("invoice_date")
            if d:
                dates.append(str(d))
    if len(dates) >= 2 and dates[0] == dates[1]:
        score += 0.15
    elif len(dates) >= 2:
        score += 0.05

    # ── Waybill number cross-reference ──────────────────────────────────────
    if tax_invoice and waybill:
        ti_ref = (tax_invoice.get("related_waybill_number") or "").strip()
        wb_num = (waybill.get("waybill_number") or "").strip()
        if ti_ref and wb_num and ti_ref == wb_num:
            score += 0.20

    # ── Presence bonus ───────────────────────────────────────────────────────
    if present == 3:
        score = min(score + 0.10, 1.0)

    score = round(min(score, 1.0), 4)
    if score >= 0.80 and not mismatches:
        status = "full"
    elif mismatches:
        status = "mismatch"
    else:
        status = "partial"

    return {
        "score": score,
        "status": status,
        "mismatches": mismatches,
    }


async def find_candidates(conn, tenant_id: str, doc_type: str, doc: dict) -> list[dict]:
    """Find matching documents of other types by INN + amount proximity."""
    candidates = []
    seller_inn = (doc.get("seller_inn") or "").strip()
    buyer_inn = (doc.get("buyer_inn") or "").strip()
    amount = _dec(doc.get("total_amount"))

    if not seller_inn and not buyer_inn:
        return candidates

    if doc_type != "waybill":
        rows = await conn.fetch(
            "SELECT id, waybill_number AS number, waybill_date AS doc_date, "
            "seller_inn, buyer_inn, total_amount "
            "FROM waybills WHERE tenant_id = $1 AND (seller_inn = $2 OR buyer_inn = $3) "
            "ORDER BY waybill_date DESC LIMIT 10",
            tenant_id, seller_inn, buyer_inn,
        )
        for r in rows:
            candidates.append({"doc_type": "waybill", "id": r["id"], "number": r["number"],
                                "doc_date": str(r["doc_date"]), "seller_inn": r["seller_inn"],
                                "buyer_inn": r["buyer_inn"], "total_amount": r["total_amount"]})

    if doc_type != "tax_invoice":
        rows = await conn.fetch(
            "SELECT id, invoice_number AS number, invoice_date AS doc_date, "
            "seller_inn, buyer_inn, total_amount "
            "FROM tax_invoices WHERE tenant_id = $1 AND (seller_inn = $2 OR buyer_inn = $3) "
            "ORDER BY invoice_date DESC LIMIT 10",
            tenant_id, seller_inn, buyer_inn,
        )
        for r in rows:
            candidates.append({"doc_type": "tax_invoice", "id": r["id"], "number": r["number"],
                                "doc_date": str(r["doc_date"]), "seller_inn": r["seller_inn"],
                                "buyer_inn": r["buyer_inn"], "total_amount": r["total_amount"]})

    if doc_type != "commercial_invoice":
        rows = await conn.fetch(
            "SELECT id, invoice_number AS number, invoice_date AS doc_date, "
            "seller_inn, buyer_inn, total_amount "
            "FROM commercial_invoices WHERE tenant_id = $1 AND (seller_inn = $2 OR buyer_inn = $3) "
            "ORDER BY invoice_date DESC LIMIT 10",
            tenant_id, seller_inn, buyer_inn,
        )
        for r in rows:
            candidates.append({"doc_type": "commercial_invoice", "id": r["id"], "number": r["number"],
                                "doc_date": str(r["doc_date"]), "seller_inn": r["seller_inn"],
                                "buyer_inn": r["buyer_inn"], "total_amount": r["total_amount"]})

    if amount is not None:
        candidates.sort(
            key=lambda c: abs(((_dec(c.get("total_amount")) or Decimal(0)) - amount))
        )
    return candidates


async def upsert_triangle_match(conn, tenant_id: str, match_data: dict) -> int:
    """Insert or update a triangle_matches row. Returns match id."""
    waybill_id = match_data.get("waybill_id")
    tax_invoice_id = match_data.get("tax_invoice_id")
    commercial_invoice_id = match_data.get("commercial_invoice_id")
    score = match_data.get("match_score", 0)
    status = match_data.get("match_status", "partial")
    mismatches = match_data.get("mismatch_fields", [])

    async with conn.transaction():
        existing = await conn.fetchrow(
            "SELECT id FROM triangle_matches WHERE tenant_id = $1 "
            "AND (waybill_id = $2 OR ($2 IS NULL AND waybill_id IS NULL)) "
            "AND (tax_invoice_id = $3 OR ($3 IS NULL AND tax_invoice_id IS NULL)) "
            "LIMIT 1",
            tenant_id, waybill_id, tax_invoice_id,
        )
        if existing:
            match_id = await conn.fetchval(
                "UPDATE triangle_matches SET "
                "tax_invoice_id=$1, commercial_invoice_id=$2, match_score=$3, match_status=$4, "
                "mismatch_fields=$5, waybill_total=$6, tax_invoice_total=$7, "
                "commercial_invoice_total=$8, amount_diff=$9, updated_at=NOW() "
                "WHERE id=$10 RETURNING id",
                tax_invoice_id, commercial_invoice_id, score, status, str(mismatches),
                match_data.get("waybill_total"), match_data.get("tax_invoice_total"),
                match_data.get("commercial_invoice_total"), match_data.get("amount_diff"),
                existing["id"],
            )
        else:
            match_id = await conn.fetchval(
                "INSERT INTO triangle_matches "
                "(tenant_id, waybill_id, tax_invoice_id, commercial_invoice_id, "
                "match_score, match_status, mismatch_fields, "
                "waybill_total, tax_invoice_total, commercial_invoice_total, amount_diff) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING id",
                tenant_id, waybill_id, tax_invoice_id, commercial_invoice_id,
                score, status, str(mismatches),
                match_data.get("waybill_total"), match_data.get("tax_invoice_total"),
                match_data.get("commercial_invoice_total"), match_data.get("amount_diff"),
            )
    return match_id
