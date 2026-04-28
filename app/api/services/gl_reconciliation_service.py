"""app/api/services/gl_reconciliation_service.py
GL ↔ Bank reconciliation: match journal_drafts entries against bank_transactions.
"""
from __future__ import annotations
import logging
from typing import Optional
from datetime import date, timedelta

from app.api.db import get_db
from app.api.response_utils import ok_response, error_response

log = logging.getLogger(__name__)

_BANK_ACCOUNTS = {"1120", "1110"}  # cash + bank in COA
_TOLERANCE_GEL = 0.05              # rounding tolerance


def _get_gl_bank_movements(tenant_id: str, date_from: str, date_to: str) -> list[dict]:
    """Return all debit/credit movements on bank/cash accounts from approved drafts."""
    sql = """
        SELECT
            jd.id             AS draft_id,
            jd.date           AS tx_date,
            jd.description    AS description,
            jd.amount         AS draft_amount,
            entry->>'dr'      AS dr_account,
            entry->>'cr'      AS cr_account,
            CAST(COALESCE(entry->>'amount', '0') AS NUMERIC) AS entry_amount
        FROM journal_drafts jd
        CROSS JOIN LATERAL jsonb_array_elements(jd.journal_entries) AS entry
        WHERE jd.tenant_id = %s
          AND jd.status IN ('approved', 'posted')
          AND jd.date BETWEEN %s AND %s
          AND (entry->>'dr' = ANY(%s) OR entry->>'cr' = ANY(%s))
        ORDER BY jd.date, jd.id
    """
    bank_codes = list(_BANK_ACCOUNTS)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(sql, (tenant_id, date_from, date_to, bank_codes, bank_codes))
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    results = []
    for draft_id, tx_date, desc, draft_amount, dr, cr, amount in rows:
        side = "debit" if dr in _BANK_ACCOUNTS else "credit"
        results.append({
            "source": "gl",
            "draft_id": draft_id,
            "date": tx_date.isoformat() if hasattr(tx_date, "isoformat") else str(tx_date),
            "description": desc or "",
            "amount": float(amount or 0),
            "side": side,
            "matched": False,
            "match_id": None,
        })
    return results


def _get_bank_transactions(tenant_id: str, date_from: str, date_to: str) -> list[dict]:
    """Return bank_transactions rows for the period."""
    sql = """
        SELECT id, date, description, amount
        FROM bank_transactions
        WHERE tenant_id = %s
          AND date BETWEEN %s AND %s
        ORDER BY date, id
    """
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(sql, (tenant_id, date_from, date_to))
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    return [
        {
            "source": "bank",
            "bank_tx_id": r[0],
            "date": r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1]),
            "description": r[2] or "",
            "amount": abs(float(r[3] or 0)),
            "side": "debit" if float(r[3] or 0) >= 0 else "credit",
            "matched": False,
            "match_id": None,
        }
        for r in rows
    ]


def _match(gl_items: list[dict], bank_items: list[dict]) -> tuple[list, list, list]:
    """Simple amount+date matching within 3-day window."""
    matched_pairs = []
    unmatched_gl = []
    unmatched_bank = list(bank_items)

    for gl in gl_items:
        best = None
        for i, bk in enumerate(unmatched_bank):
            if bk["matched"]:
                continue
            if bk["side"] != gl["side"]:
                continue
            if abs(bk["amount"] - gl["amount"]) > _TOLERANCE_GEL:
                continue
            # Date within ±3 days
            try:
                gl_d  = date.fromisoformat(gl["date"])
                bk_d  = date.fromisoformat(bk["date"])
                if abs((gl_d - bk_d).days) <= 3:
                    best = i
                    break
            except Exception:
                continue

        if best is not None:
            unmatched_bank[best]["matched"] = True
            gl["matched"] = True
            matched_pairs.append({"gl": gl, "bank": unmatched_bank[best]})
        else:
            unmatched_gl.append(gl)

    remaining_bank = [b for b in unmatched_bank if not b["matched"]]
    return matched_pairs, unmatched_gl, remaining_bank


def reconcile_gl_bank(
    tenant_id: str,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
) -> dict:
    today = date.today()
    df = date_from or (today.replace(day=1)).isoformat()
    dt = date_to   or today.isoformat()

    try:
        gl_items   = _get_gl_bank_movements(tenant_id, df, dt)
        bank_items = _get_bank_transactions(tenant_id, df, dt)
    except Exception as e:
        log.error("GL recon data fetch failed: %s", e)
        return error_response("GL reconciliation failed", "DB_ERROR", str(e))

    matched, unmatched_gl, unmatched_bank = _match(gl_items, bank_items)

    gl_total   = round(sum(i["amount"] for i in gl_items), 2)
    bank_total = round(sum(i["amount"] for i in bank_items), 2)
    diff       = round(gl_total - bank_total, 2)

    return ok_response("GL reconciliation complete", {
        "period":          {"from": df, "to": dt},
        "summary": {
            "gl_movements":     len(gl_items),
            "bank_transactions": len(bank_items),
            "matched":          len(matched),
            "unmatched_gl":     len(unmatched_gl),
            "unmatched_bank":   len(unmatched_bank),
            "gl_total":         gl_total,
            "bank_total":       bank_total,
            "difference":       diff,
            "status":           "balanced" if abs(diff) <= _TOLERANCE_GEL else "unbalanced",
        },
        "matched_pairs":   matched,
        "unmatched_gl":    unmatched_gl,
        "unmatched_bank":  unmatched_bank,
    })
