"""app/api/services/ai_context_builder.py
Bridge Hub — AI Context Builder (STEP 1.2)
Builds a rich context dict that gets passed to LLM on every document analysis.
"""
import logging

from app.api.db import get_conn, _q
from app.knowledge.chart_of_accounts import CHART_OF_ACCOUNTS, TAX_RATES
from app.knowledge.tax_rules import TAX_RULES

log = logging.getLogger(__name__)


async def get_vendor_patterns(tenant_id: str) -> list[dict]:
    """Return top learned patterns for this tenant (used as AI hints)."""
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(_q("""
                SELECT keyword, account_code, confidence_score
                FROM learning_patterns
                WHERE tenant_id = %s AND active = TRUE
                ORDER BY confidence_score DESC
                LIMIT 50
            """), tenant_id)
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning("vendor_patterns query failed: %s", e)
        return []


async def get_recent_drafts_summary(tenant_id: str, limit: int = 10) -> list[dict]:
    """Return recent approved drafts — helps LLM with partner→account consistency."""
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(_q("""
                SELECT description, account_dr, account_cr, amount
                FROM journal_drafts
                WHERE tenant_id = %s AND status = 'approved'
                ORDER BY created_at DESC
                LIMIT %s
            """), tenant_id, limit)
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning("recent_drafts query failed: %s", e)
        return []


async def get_bank_summary(tenant_id: str) -> dict:
    """Return unreconciled bank transaction count + total unmatched amount (last 90 days)."""
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q("""
                SELECT
                    COUNT(*) AS total_transactions,
                    COUNT(*) FILTER (
                        WHERE NOT EXISTS (
                            SELECT 1 FROM bank_reconciliations br
                            WHERE br.bank_transaction_id::text = bt.id::text
                              AND br.tenant_id = bt.tenant_id
                        )
                    ) AS unreconciled,
                    COALESCE(SUM(ABS(bt.amount)), 0) AS total_volume
                FROM bank_transactions bt
                WHERE bt.tenant_id = %s
                  AND bt.date >= NOW() - INTERVAL '90 days'
            """), tenant_id)
        return {
            "total_transactions_90d": int(row["total_transactions"] or 0),
            "unreconciled_count": int(row["unreconciled"] or 0),
            "total_volume_gel": round(float(row["total_volume"] or 0), 2),
        }
    except Exception as e:
        log.warning("bank_summary query failed: %s", e)
        return {}


async def get_active_contracts_summary(tenant_id: str) -> list[dict]:
    """Return active contracts count + overdue milestones for AI context."""
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(_q("""
                SELECT c.party_name, c.contract_type, c.value, c.currency,
                       c.end_date, c.status,
                       COUNT(cm.id) FILTER (
                           WHERE cm.status = 'pending' AND cm.due_date < NOW()
                       ) AS overdue_milestones
                FROM contracts c
                LEFT JOIN contract_milestones cm
                    ON cm.contract_id = c.id AND cm.tenant_id = c.tenant_id
                WHERE c.tenant_id = %s
                  AND c.status NOT IN ('cancelled','expired','terminated')
                  AND (c.end_date IS NULL OR c.end_date >= NOW())
                GROUP BY c.id
                ORDER BY c.value DESC NULLS LAST
                LIMIT 10
            """), tenant_id)
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning("active_contracts_summary query failed: %s", e)
        return []


async def build_ai_context(tenant_id: str) -> dict:
    """
    Build the full context dict passed to LLM on every document analysis.
    Includes COA, Georgian tax rules, learned vendor patterns, recent history,
    bank summary, and active contracts.
    """
    coa_summary = {
        code: info.get("name", "") if isinstance(info, dict) else str(info)
        for code, info in CHART_OF_ACCOUNTS.items()
    }

    import asyncio
    vendor_patterns, recent_drafts, bank_summary, active_contracts = await asyncio.gather(
        get_vendor_patterns(tenant_id),
        get_recent_drafts_summary(tenant_id),
        get_bank_summary(tenant_id),
        get_active_contracts_summary(tenant_id),
    )

    return {
        "tenant_id": tenant_id,
        "chart_of_accounts": coa_summary,
        "tax_rules": {
            "vat_rate": round(TAX_RATES.get("vat", 0.18) * 100),
            "pit_rate": round(TAX_RATES.get("pit", 0.20) * 100),
            "payg_rate": round(TAX_RATES.get("payg_employee", 0.02) * 100),
            "cit_rate": round(TAX_RATES.get("cit", 0.15) * 100),
            "vat_threshold_gel": TAX_RATES.get("vat_threshold", 100000),
        },
        "vendor_patterns": vendor_patterns,
        "recent_drafts": recent_drafts,
        "bank_summary": bank_summary,
        "active_contracts": active_contracts,
    }
