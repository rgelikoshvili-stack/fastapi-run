"""app/api/services/bank_brain_service.py — Bank Brain (Task 14).

Adds intelligence on top of the existing reconciliation engine:
  - compute_reconciliation_health  — % reconciled + discrepancy amount
  - extract_match_patterns         — pure: learn partner→account from confirmed matches
  - suggest_categories_for_unmatched — apply learned patterns to uncategorised bank txns
  - get_aged_unreconciled          — bucket unreconciled drafts by age (30/60/90 days)
  - get_bank_brain_summary         — full async health + aged summary for a tenant
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.api.db import get_conn, _q

# Age buckets in days
AGE_BUCKETS = [30, 60, 90]


# ---------------------------------------------------------------------------
# Pure functions (no DB access)
# ---------------------------------------------------------------------------

def extract_match_patterns(auto_matched: list[dict]) -> list[dict]:
    """Learn partner → account_code patterns from a set of confirmed auto-matches.

    Each pattern:
        {"partner": str, "account_code": str, "occurrences": int, "avg_amount": float}
    """
    from collections import defaultdict
    tally: dict[tuple, list[float]] = defaultdict(list)

    for item in auto_matched:
        draft = item.get("matched_draft") or item.get("draft") or {}
        partner = str(draft.get("partner") or "").strip().lower()
        account = str(draft.get("account_code") or "").strip()
        amount  = float(draft.get("amount") or 0)
        if partner and account:
            tally[(partner, account)].append(amount)

    patterns = []
    for (partner, account), amounts in tally.items():
        patterns.append({
            "partner": partner,
            "account_code": account,
            "occurrences": len(amounts),
            "avg_amount": round(sum(amounts) / len(amounts), 2),
        })
    return sorted(patterns, key=lambda p: p["occurrences"], reverse=True)


def suggest_categories_for_unmatched(
    unmatched_bank: list[dict],
    patterns: list[dict],
) -> list[dict]:
    """Suggest a likely account_code for each unmatched bank transaction.

    Uses simple partner-name substring matching against learned patterns.
    Returns the original transaction enriched with:
        "suggested_account": str | None
        "suggestion_confidence": "high" | "low" | None
        "suggestion_reason": str | None
    """
    results = []
    for txn in unmatched_bank:
        description = str(txn.get("description") or txn.get("reference") or "").lower()
        best_pattern = None
        best_score   = 0

        for pat in patterns:
            partner = pat["partner"].lower()
            if partner and partner in description:
                score = pat["occurrences"]
                if score > best_score:
                    best_score   = score
                    best_pattern = pat

        enriched = dict(txn)
        if best_pattern:
            enriched["suggested_account"]    = best_pattern["account_code"]
            enriched["suggestion_confidence"] = "high" if best_score >= 3 else "low"
            enriched["suggestion_reason"]    = (
                f"Partner '{best_pattern['partner']}' matched {best_score}x in history"
            )
        else:
            enriched["suggested_account"]    = None
            enriched["suggestion_confidence"] = None
            enriched["suggestion_reason"]    = None
        results.append(enriched)
    return results


def bucket_by_age(items: list[dict], reference_date: date | None = None) -> dict[str, list]:
    """Bucket items by age of their 'created_at' or 'transaction_date' field.

    Buckets: "0_30d", "31_60d", "61_90d", "over_90d"
    """
    ref = reference_date or date.today()
    buckets: dict[str, list] = {"0_30d": [], "31_60d": [], "61_90d": [], "over_90d": []}

    for item in items:
        raw = item.get("created_at") or item.get("transaction_date") or ""
        try:
            item_date = date.fromisoformat(str(raw)[:10])
        except ValueError:
            buckets["over_90d"].append(item)
            continue
        age = (ref - item_date).days
        if age <= 30:
            buckets["0_30d"].append(item)
        elif age <= 60:
            buckets["31_60d"].append(item)
        elif age <= 90:
            buckets["61_90d"].append(item)
        else:
            buckets["over_90d"].append(item)
    return buckets


# ---------------------------------------------------------------------------
# Async service functions
# ---------------------------------------------------------------------------

async def compute_reconciliation_health(
    tenant_id: str,
    month: str | None = None,
) -> dict[str, Any]:
    """Return reconciliation health metrics for *month* (YYYY-MM).

    If month is None, uses the current month.
    """
    if not month:
        today = date.today()
        month = today.strftime("%Y-%m")

    month_start = f"{month}-01"
    # last day: first day of next month minus 1
    y, m = int(month[:4]), int(month[5:7])
    if m == 12:
        month_end = f"{y+1}-01-01"
    else:
        month_end = f"{y}-{m+1:02d}-01"

    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""
                SELECT
                    COUNT(*)                                        AS total_drafts,
                    COUNT(*) FILTER (WHERE reconciled = TRUE)       AS reconciled_count,
                    COUNT(*) FILTER (WHERE reconciled IS NOT TRUE)  AS unreconciled_count,
                    COALESCE(SUM(amount) FILTER (WHERE reconciled IS NOT TRUE), 0)
                                                                    AS unreconciled_amount,
                    COALESCE(SUM(amount), 0)                        AS total_amount
                FROM journal_drafts
                WHERE tenant_id = $1
                  AND status IN ('posted', 'approved', 'awaiting_cfo')
                  AND created_at >= $2
                  AND created_at <  $3
            """),
            tenant_id, month_start, month_end,
        )

    total     = int(row["total_drafts"])
    recon     = int(row["reconciled_count"])
    unrecon   = int(row["unreconciled_count"])
    unr_amt   = round(float(row["unreconciled_amount"]), 2)
    total_amt = round(float(row["total_amount"]), 2)

    health_pct = round(recon / total * 100, 1) if total else 100.0
    if health_pct >= 90:
        health_status = "healthy"
    elif health_pct >= 70:
        health_status = "warning"
    else:
        health_status = "critical"

    return {
        "month": month,
        "total_drafts": total,
        "reconciled_count": recon,
        "unreconciled_count": unrecon,
        "reconciliation_rate_pct": health_pct,
        "unreconciled_amount": unr_amt,
        "total_amount": total_amt,
        "health_status": health_status,
    }


async def get_aged_unreconciled(
    tenant_id: str,
    limit: int = 200,
) -> dict[str, Any]:
    """Return unreconciled posted/approved drafts bucketed by age."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            _q("""
                SELECT id, description, amount, partner,
                       status, created_at, account_code
                FROM journal_drafts
                WHERE tenant_id = $1
                  AND status IN ('posted', 'approved', 'awaiting_cfo')
                  AND (reconciled IS NOT TRUE)
                ORDER BY created_at ASC
                LIMIT $2
            """),
            tenant_id, limit,
        )

    items = [dict(r) for r in rows]
    buckets = bucket_by_age(items)
    total_unreconciled_amount = round(sum(float(i.get("amount") or 0) for i in items), 2)

    return {
        "total_unreconciled": len(items),
        "total_unreconciled_amount": total_unreconciled_amount,
        "buckets": {k: {"count": len(v), "items": v} for k, v in buckets.items()},
    }


async def get_bank_brain_summary(
    tenant_id: str,
    month: str | None = None,
) -> dict[str, Any]:
    """Full Bank Brain summary: health + aged unreconciled."""
    health = await compute_reconciliation_health(tenant_id, month)
    aged   = await get_aged_unreconciled(tenant_id)
    return {
        "health": health,
        "aged_unreconciled": aged,
    }
