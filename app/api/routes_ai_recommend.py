"""
app/api/routes_ai_recommend.py
Bridge Hub — Proactive Assistant (read-only recommendations)

GET /api/ai/recommend
- reads pending journal_drafts
- groups by pattern similarity
- returns actionable suggestions
NO writes, NO auto-creates drafts.
"""

import logging
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Request, Query

from app.api.db import get_conn, _q
from app.api.tenant_context import resolve_tenant_id

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["AI Assistant"])

_PATTERN_HINTS = [
    (["იჯარა", "rent", "office rent", "სოფ. ოფ"], "rent", "იჯარის გადახდა"),
    (["ხელფასი", "salary", "payroll", "bonus"], "payroll", "ხელფასის ოპერაცია"),
    (["vat", "დღგ", "tax invoice"], "vat", "დღგ-ს ოპერაცია"),
    (["amazon", "aws", "google cloud", "azure"], "cloud", "Cloud ხარჯი"),
    (["facebook", "google ads", "advertising", "მარკეტინგი"], "marketing", "მარკეტინგის ხარჯი"),
    (["cit", "pit", "საგადასახადო", "tax payment"], "tax", "გადასახადის გადახდა"),
    (["invoice", "ინვოისი"], "invoice", "ინვოისის გადახდა"),
    (["comission", "commission", "საკომისიო", "bank fee"], "bank_fee", "საბანკო საკომისიო"),
]


def _detect_pattern(description: str) -> tuple[str, str]:
    desc_lower = (description or "").lower()
    for keywords, key, label in _PATTERN_HINTS:
        if any(kw in desc_lower for kw in keywords):
            return key, label
    return "other", "სხვა"


def _build_recommendations(drafts: list) -> list:
    groups: dict = defaultdict(list)
    for d in drafts:
        key, label = _detect_pattern(d.get("description") or "")
        groups[(key, label)].append(d)

    recommendations = []

    for (key, label), items in groups.items():
        if key == "other" and len(items) < 2:
            continue

        total = sum(float(d.get("amount") or 0) for d in items)
        ids = [d["id"] for d in items]
        oldest = min((str(d.get("date") or "") for d in items), default="")

        if len(items) == 1:
            msg = f"ნაპოვნია 1 ტრანზაქცია: {label} — {total:,.2f} GEL (draft #{ids[0]})"
        else:
            msg = f"ნაპოვნია {len(items)} ტრანზაქცია, რომელიც ჰგავს {label}-ს — ჯამი: {total:,.2f} GEL"

        recommendations.append({
            "pattern": key,
            "label": label,
            "count": len(items),
            "total_amount": round(total, 2),
            "draft_ids": ids,
            "oldest_date": oldest,
            "message": msg,
            "action": "review_and_approve",
        })

    recommendations.sort(key=lambda r: r["count"], reverse=True)
    return recommendations


def _high_value_alert(drafts: list, threshold: float = 5000.0) -> list:
    alerts = []
    for d in drafts:
        amount = float(d.get("amount") or 0)
        if amount >= threshold:
            alerts.append({
                "pattern": "high_value",
                "label": "დიდი თანხის ოპერაცია",
                "count": 1,
                "total_amount": amount,
                "draft_ids": [d["id"]],
                "oldest_date": str(d.get("date") or ""),
                "message": (
                    f"დიდი თანხა: {d.get('description') or 'N/A'} — "
                    f"{amount:,.2f} GEL (draft #{d['id']})"
                ),
                "action": "review_carefully",
            })
    return alerts


@router.get("/recommend")
async def get_recommendations(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    high_value_threshold: Optional[float] = Query(5000.0),
):
    """Read-only proactive suggestions based on pending journal drafts."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        async with get_conn() as conn:
            drafts = [dict(r) for r in await conn.fetch(_q("""
                SELECT id, description, partner, amount, currency,
                       account_code, date, status
                FROM journal_drafts
                WHERE tenant_id = %s AND status IN ('pending_approval', 'pending')
                ORDER BY created_at DESC LIMIT %s
            """), tenant_id, limit)]
    except Exception as e:
        log.error("recommend: DB error tenant=%s: %s", tenant_id, e)
        drafts = []

    pattern_recs = _build_recommendations(drafts)
    high_value = _high_value_alert(drafts, threshold=high_value_threshold or 5000.0)
    all_recs = high_value + pattern_recs

    summary = (
        f"ნაპოვნია {len(drafts)} pending draft. {len(all_recs)} რეკომენდაცია."
        if drafts else "Pending drafts არ არის."
    )

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "pending_count": len(drafts),
        "recommendations": all_recs,
        "summary": summary,
        "mode": "read_only",
    }
