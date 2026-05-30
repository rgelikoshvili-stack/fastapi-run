"""
app/context_memory/context_builder.py
Bridge Hub — Context Builder
ამოიღებს კონტექსტს transaction-ისთვის classification-ის გასაუმჯობესებლად.
Core classification არ იცვლება — ეს მხოლოდ optional enrichment-ია.
"""
from app.api.db import get_conn, _q


async def build_context_for_transaction(transaction: dict, tenant_id: str = "default") -> dict:
    try:
        context = {
            "similar_cases": await _get_similar_cases(transaction, tenant_id),
            "historical_corrections": await _get_historical_corrections(transaction, tenant_id),
            "tenant_memory": await _get_tenant_memory(transaction, tenant_id),
            "partner_history": await _get_partner_history(transaction, tenant_id),
        }
        context["has_context"] = any(len(v) > 0 for v in context.values() if isinstance(v, list))
        return context
    except Exception as e:
        return {"has_context": False, "error": str(e)}


async def _get_similar_cases(transaction: dict, tenant_id: str) -> list:
    description = (transaction.get("description") or "").strip()
    if not description:
        return []
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(_q("""
                SELECT description, account_code, debit_account, credit_account,
                       amount, status, confidence
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND status IN ('approved', 'auto_approved')
                  AND LOWER(description) LIKE LOWER(%s)
                ORDER BY created_at DESC LIMIT 5
            """), tenant_id, f"%{description[:20]}%")
        return [dict(r) for r in rows]
    except Exception:
        return []


async def _get_historical_corrections(transaction: dict, tenant_id: str) -> list:
    description = (transaction.get("description") or "").strip()
    if not description:
        return []
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(_q("""
                SELECT description, account_code, reason, approved_by_mode
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND approved_by_mode IN ('human_correction', 'manual_review')
                  AND LOWER(description) LIKE LOWER(%s)
                ORDER BY updated_at DESC LIMIT 3
            """), tenant_id, f"%{description[:20]}%")
        return [dict(r) for r in rows]
    except Exception:
        return []


async def _get_tenant_memory(transaction: dict, tenant_id: str) -> list:
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(_q("""
                SELECT pattern_value, account_code, confidence_score,
                       support_count, success_count
                FROM learning_patterns
                WHERE tenant_id = %s AND status = 'active'
                ORDER BY confidence_score DESC LIMIT 10
            """), tenant_id)
        return [dict(r) for r in rows]
    except Exception:
        return []


async def _get_partner_history(transaction: dict, tenant_id: str) -> list:
    partner = (transaction.get("partner") or "").strip()
    if not partner:
        return []
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(_q("""
                SELECT account_code, debit_account, credit_account,
                       COUNT(*) as frequency, AVG(amount) as avg_amount
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND LOWER(partner) = LOWER(%s)
                  AND status IN ('approved', 'auto_approved')
                GROUP BY account_code, debit_account, credit_account
                ORDER BY frequency DESC LIMIT 3
            """), tenant_id, partner)
        return [dict(r) for r in rows]
    except Exception:
        return []


def build_context_summary(context: dict) -> str:
    if not context.get("has_context"):
        return ""

    lines = []

    similar = context.get("similar_cases", [])
    if similar:
        lines.append("წინა მსგავსი ტრანზაქციები:")
        for s in similar[:3]:
            lines.append(
                f"  - {s.get('description', '')} → "
                f"{s.get('account_code', '')} "
                f"(confidence: {s.get('confidence', '')})"
            )

    corrections = context.get("historical_corrections", [])
    if corrections:
        lines.append("ადამიანის კორექციები:")
        for c in corrections[:2]:
            lines.append(
                f"  - {c.get('description', '')} → "
                f"{c.get('account_code', '')} ({c.get('reason', '')})"
            )

    partner = context.get("partner_history", [])
    if partner:
        lines.append("პარტნიორის ისტორია:")
        for p in partner[:2]:
            lines.append(
                f"  - ანგარიში: {p.get('account_code', '')} "
                f"({p.get('frequency', 0)} ჯერ, "
                f"საშ. {p.get('avg_amount', 0):.2f} GEL)"
            )

    return "\n".join(lines)
