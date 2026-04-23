"""app/api/services/ai_context_builder.py
Bridge Hub — AI Context Builder (STEP 1.2)
Builds a rich context dict that gets passed to LLM on every document analysis.
"""
import logging
import os
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from app.knowledge.chart_of_accounts import CHART_OF_ACCOUNTS, TAX_RATES
from app.knowledge.tax_rules import TAX_RULES

log = logging.getLogger(__name__)


def _get_db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not configured")
    return psycopg2.connect(url)


def get_vendor_patterns(tenant_id: str) -> list[dict]:
    """Return top learned patterns for this tenant (used as AI hints)."""
    try:
        conn = _get_db()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT keyword, account_code, confidence_score
                FROM learning_patterns
                WHERE tenant_id = %s AND active = TRUE
                ORDER BY confidence_score DESC
                LIMIT 50
                """,
                (tenant_id,),
            )
            rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning("vendor_patterns query failed: %s", e)
        return []


def get_recent_drafts_summary(tenant_id: str, limit: int = 10) -> list[dict]:
    """Return recent approved drafts — helps LLM with partner→account consistency."""
    try:
        conn = _get_db()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT description, account_dr, account_cr, amount
                FROM journal_drafts
                WHERE tenant_id = %s AND status = 'approved'
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (tenant_id, limit),
            )
            rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning("recent_drafts query failed: %s", e)
        return []


def build_ai_context(tenant_id: str) -> dict:
    """
    Build the full context dict passed to LLM on every document analysis.
    Includes COA, Georgian tax rules, learned vendor patterns, and recent history.
    """
    # Top-level COA: just codes + names to keep token count low
    coa_summary = {
        code: info.get("name", "") if isinstance(info, dict) else str(info)
        for code, info in CHART_OF_ACCOUNTS.items()
    }

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
        "vendor_patterns": get_vendor_patterns(tenant_id),
        "recent_drafts": get_recent_drafts_summary(tenant_id),
    }
