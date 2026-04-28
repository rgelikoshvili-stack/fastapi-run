"""app/api/services/reconciliation_service.py — Smart bank reconciliation matching.

Matching algorithm (scored, multi-signal):
  1. Exact amount + date ±3 days                → score 100 (auto-match)
  2. Exact amount + partner name similarity      → score 85
  3. Exact amount within date window ±7 days     → score 70
  4. Amount within 1% tolerance + date ±3 days  → score 60
  5. Reference number match (invoice/PO number) → score 95 (auto-match)

Threshold: score ≥ 85 → auto_matched, score 50-84 → suggested, <50 → unmatched
"""
from __future__ import annotations
import logging
import re
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Optional

log = logging.getLogger(__name__)

AUTO_MATCH_THRESHOLD = 85
SUGGEST_THRESHOLD = 50


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _extract_ref(text: str) -> Optional[str]:
    """Extract invoice/PO reference numbers from transaction description."""
    if not text:
        return None
    patterns = [
        r'\b(?:INV|ანგ|ФАК|PO|ORD|REF|#)[-\s]?(\d{4,})\b',
        r'\b(\d{6,})\b',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def match_transactions(
    bank_txn: dict,
    candidates: list[dict],
    amount_tolerance: float = 0.01,
    date_window_days: int = 7,
) -> list[dict]:
    """
    Score each candidate journal draft against a bank transaction.

    Returns list of candidates with 'match_score' and 'match_reason' added,
    sorted by score descending.
    """
    bank_amount = Decimal(str(abs(bank_txn.get("amount", 0))))
    bank_date = bank_txn.get("transaction_date")
    if isinstance(bank_date, str):
        bank_date = date.fromisoformat(bank_date[:10])
    bank_desc = str(bank_txn.get("description", ""))
    bank_ref = _extract_ref(bank_desc)

    results = []

    for cand in candidates:
        score = 0
        reasons = []

        cand_amount = Decimal(str(abs(cand.get("amount", 0))))
        cand_date = cand.get("transaction_date") or cand.get("date")
        if isinstance(cand_date, str):
            cand_date = date.fromisoformat(str(cand_date)[:10])
        cand_desc = str(cand.get("description", "") or cand.get("partner", ""))
        cand_ref = _extract_ref(cand_desc) or str(cand.get("invoice_number", "") or "")

        # Signal 1: Reference number match (strongest)
        if bank_ref and cand_ref and bank_ref == cand_ref:
            score += 95
            reasons.append(f"ref_match:{bank_ref}")

        # Signal 2: Exact amount
        amount_diff = abs(bank_amount - cand_amount)
        if amount_diff == 0:
            score += 40
            reasons.append("exact_amount")
        elif bank_amount > 0:
            pct_diff = float(amount_diff / bank_amount)
            if pct_diff <= amount_tolerance:
                score += 20
                reasons.append(f"amount_within_{amount_tolerance*100:.0f}pct")

        # Signal 3: Date proximity
        if bank_date and cand_date:
            days_diff = abs((bank_date - cand_date).days)
            if days_diff == 0:
                score += 30
                reasons.append("same_date")
            elif days_diff <= 3:
                score += 20
                reasons.append(f"date_±{days_diff}d")
            elif days_diff <= date_window_days:
                score += 10
                reasons.append(f"date_±{days_diff}d")

        # Signal 4: Description/partner similarity
        sim = _similarity(bank_desc, cand_desc)
        if sim >= 0.8:
            score += 20
            reasons.append(f"desc_sim:{sim:.0%}")
        elif sim >= 0.5:
            score += 10
            reasons.append(f"desc_sim:{sim:.0%}")

        if score >= SUGGEST_THRESHOLD:
            result = dict(cand)
            result["match_score"] = min(score, 100)
            result["match_reason"] = ", ".join(reasons)
            result["match_status"] = "auto_matched" if score >= AUTO_MATCH_THRESHOLD else "suggested"
            results.append(result)

    return sorted(results, key=lambda x: x["match_score"], reverse=True)


def reconcile_bank_statement(conn, tenant_id: str,
                              bank_transactions: list[dict],
                              date_from: date = None,
                              date_to: date = None) -> dict:
    """
    Main reconciliation function.
    Matches bank transactions against unreconciled journal_drafts.

    Returns:
        {
          "auto_matched": [...],
          "suggested": [...],
          "unmatched_bank": [...],
          "unmatched_drafts": [...],
          "summary": {...}
        }
    """
    cur = conn.cursor()

    try:
        # Load unreconciled journal drafts in date range
        params = [tenant_id]
        date_filter = ""
        if date_from:
            date_filter += " AND (transaction_date >= %s OR created_at >= %s)"
            params += [date_from, date_from]
        if date_to:
            date_filter += " AND (transaction_date <= %s OR created_at <= %s)"
            params += [date_to, date_to]

        cur.execute(f"""
            SELECT id, description, amount, transaction_date,
                   partner, account_code, status, currency
            FROM journal_drafts
            WHERE tenant_id = %s
              AND status IN ('approved', 'drafted', 'pending_approval')
              AND (reconciled = FALSE OR reconciled IS NULL)
              {date_filter}
            ORDER BY transaction_date DESC
            LIMIT 500
        """, params)
        cols = [d[0] for d in cur.description]
        unmatched_drafts = [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        log.warning("reconcile load drafts failed: %s", e)
        unmatched_drafts = []
    finally:
        cur.close()

    auto_matched = []
    suggested_matches = []
    unmatched_bank = []
    used_draft_ids = set()

    for txn in bank_transactions:
        available = [d for d in unmatched_drafts if d["id"] not in used_draft_ids]
        matches = match_transactions(txn, available)

        if not matches:
            unmatched_bank.append(txn)
            continue

        best = matches[0]
        if best["match_status"] == "auto_matched":
            auto_matched.append({
                "bank_transaction": txn,
                "matched_draft": best,
                "score": best["match_score"],
                "reason": best["match_reason"],
            })
            used_draft_ids.add(best["id"])
        else:
            suggested_matches.append({
                "bank_transaction": txn,
                "candidates": matches[:3],
                "top_score": best["match_score"],
            })

    remaining_drafts = [d for d in unmatched_drafts if d["id"] not in used_draft_ids]

    return {
        "auto_matched": auto_matched,
        "suggested": suggested_matches,
        "unmatched_bank": unmatched_bank,
        "unmatched_drafts": remaining_drafts,
        "summary": {
            "bank_transactions": len(bank_transactions),
            "auto_matched_count": len(auto_matched),
            "suggested_count": len(suggested_matches),
            "unmatched_bank_count": len(unmatched_bank),
            "unmatched_draft_count": len(remaining_drafts),
            "match_rate_pct": round(
                len(auto_matched) / max(len(bank_transactions), 1) * 100, 1
            ),
        },
    }


def apply_reconciliation(conn, tenant_id: str, matches: list[dict]) -> int:
    """
    Persist confirmed matches — mark draft as reconciled, link to bank txn.
    Returns number of records updated.
    """
    cur = conn.cursor()
    count = 0
    try:
        # Ensure column exists
        cur.execute("""
            ALTER TABLE journal_drafts
                ADD COLUMN IF NOT EXISTS reconciled BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS reconciled_at TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS bank_txn_id TEXT
        """)

        for match in matches:
            draft_id = match.get("draft_id")
            bank_txn_id = str(match.get("bank_txn_id", ""))
            if not draft_id:
                continue
            cur.execute("""
                UPDATE journal_drafts
                SET reconciled = TRUE, reconciled_at = NOW(), bank_txn_id = %s
                WHERE id = %s AND tenant_id = %s
            """, (bank_txn_id, draft_id, tenant_id))
            count += cur.rowcount
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.warning("apply_reconciliation failed: %s", e)
    finally:
        cur.close()
    return count
