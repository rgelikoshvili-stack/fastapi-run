"""
app/api/services/chat_context_service.py
Bridge Hub — Chat Context Builder

Fetches real DB data for Claude so it never has to invent anything.
All queries are tenant-scoped (WHERE tenant_id = %s).
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import psycopg2.extras

from app.api.db import get_db

log = logging.getLogger(__name__)


def build_chat_context(
    tenant_id: str,
    message: str,
    draft_id: Optional[int] = None,
) -> dict:
    """
    Build structured context dict for Claude.

    Returns:
        {
          "draft": dict | None,          # specific draft if draft_id given
          "pending_count": int,
          "recent_drafts": [...],
          "bank_accounts": [...],
          "kpi": dict | None,
          "not_found": bool,             # True if draft_id given but not found
        }
    """
    ctx: dict = {
        "draft": None,
        "pending_count": 0,
        "recent_drafts": [],
        "bank_accounts": [],
        "kpi": None,
        "not_found": False,
    }

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. Specific draft by ID
        if draft_id is not None:
            try:
                cur.execute(
                    """
                    SELECT id, description, amount, partner, account_code,
                           debit_account, credit_account, status, confidence,
                           source_type, created_at, date
                    FROM journal_drafts
                    WHERE id = %s AND tenant_id = %s
                    """,
                    (draft_id, tenant_id),
                )
                row = cur.fetchone()
                if row:
                    ctx["draft"] = dict(row)
                    # Convert Decimal/datetime for JSON
                    if ctx["draft"].get("amount") is not None:
                        ctx["draft"]["amount"] = float(ctx["draft"]["amount"])
                    if ctx["draft"].get("confidence") is not None:
                        ctx["draft"]["confidence"] = float(ctx["draft"]["confidence"])
                    if ctx["draft"].get("created_at"):
                        ctx["draft"]["created_at"] = str(ctx["draft"]["created_at"])
                    if ctx["draft"].get("date"):
                        ctx["draft"]["date"] = str(ctx["draft"]["date"])
                else:
                    ctx["not_found"] = True
            except Exception as e:
                log.warning("draft fetch failed: %s", e)

        # 2. Pending drafts count
        try:
            cur.execute(
                "SELECT COUNT(*) as cnt FROM journal_drafts "
                "WHERE status IN ('pending_approval','drafted') AND tenant_id = %s",
                (tenant_id,),
            )
            row = cur.fetchone()
            ctx["pending_count"] = int(row["cnt"]) if row else 0
        except Exception as e:
            log.warning("pending count failed: %s", e)

        # 3. Recent drafts (last 5, excluding the specific one already fetched)
        try:
            exclude_id = draft_id if draft_id is not None else -1
            cur.execute(
                """
                SELECT id, description, amount, partner, status, account_code, created_at
                FROM journal_drafts
                WHERE tenant_id = %s AND id != %s
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (tenant_id, exclude_id),
            )
            rows = cur.fetchall()
            ctx["recent_drafts"] = [
                {
                    "id": r["id"],
                    "description": r["description"],
                    "amount": float(r["amount"]) if r["amount"] else 0,
                    "partner": r["partner"],
                    "status": r["status"],
                    "account_code": r["account_code"],
                }
                for r in rows
            ]
        except Exception as e:
            log.warning("recent drafts failed: %s", e)

        # 4. Bank accounts
        try:
            cur.execute(
                "SELECT name, balance, currency, account_type "
                "FROM bank_accounts WHERE tenant_id = %s ORDER BY balance DESC LIMIT 5",
                (tenant_id,),
            )
            rows = cur.fetchall()
            ctx["bank_accounts"] = [
                {
                    "name": r["name"],
                    "balance": float(r["balance"]) if r["balance"] else 0,
                    "currency": r["currency"],
                    "type": r["account_type"],
                }
                for r in rows
            ]
        except Exception as e:
            log.warning("bank accounts failed: %s", e)

        # 5. KPI summary
        try:
            cur.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN status='pending_approval' THEN 1 END) as pending,
                    COUNT(CASE WHEN status IN ('approved','auto_approved') THEN 1 END) as approved,
                    COALESCE(AVG(confidence), 0) as avg_confidence
                FROM journal_drafts
                WHERE tenant_id = %s
                """,
                (tenant_id,),
            )
            row = cur.fetchone()
            if row:
                ctx["kpi"] = {
                    "total_drafts": int(row["total"]),
                    "pending": int(row["pending"]),
                    "approved": int(row["approved"]),
                    "avg_confidence": round(float(row["avg_confidence"]), 3),
                }
        except Exception as e:
            log.warning("kpi failed: %s", e)

        cur.close()
        conn.close()

    except Exception as e:
        log.error("build_chat_context failed: %s", e)

    return ctx


def format_context_for_prompt(ctx: dict) -> str:
    """
    Convert context dict → text block for Claude's prompt.
    Returns empty string if nothing useful.
    """
    if ctx.get("not_found"):
        return "REAL SYSTEM CONTEXT:\nდრაფტი სისტემაში ვერ მოიძებნა."

    lines = ["REAL SYSTEM CONTEXT:"]
    has_data = False

    if ctx.get("draft"):
        d = ctx["draft"]
        has_data = True
        lines.append(f"Current Draft #{d.get('id')}:")
        lines.append(f"  Description : {d.get('description')}")
        lines.append(f"  Amount      : {d.get('amount', 0):,.2f} GEL")
        lines.append(f"  Partner     : {d.get('partner') or 'N/A'}")
        lines.append(f"  Account     : {d.get('account_code') or 'N/A'}")
        lines.append(f"  Debit Acc   : {d.get('debit_account') or 'N/A'}")
        lines.append(f"  Credit Acc  : {d.get('credit_account') or 'N/A'}")
        lines.append(f"  Status      : {d.get('status')}")
        lines.append(f"  Confidence  : {d.get('confidence', 0):.0%}")
        lines.append(f"  Date        : {d.get('date') or d.get('created_at', 'N/A')}")

    if ctx.get("kpi"):
        k = ctx["kpi"]
        has_data = True
        lines.append(
            f"System KPI: total={k['total_drafts']} | pending={k['pending']} | "
            f"approved={k['approved']} | avg_confidence={k['avg_confidence']:.0%}"
        )

    if ctx.get("pending_count"):
        has_data = True
        lines.append(f"Pending approval queue: {ctx['pending_count']} drafts")

    if ctx.get("recent_drafts"):
        has_data = True
        lines.append("Recent Drafts:")
        for d in ctx["recent_drafts"]:
            lines.append(
                f"  #{d['id']} | {d['description']} | "
                f"{d['amount']:,.2f} GEL | {d['status']} | acct:{d['account_code']}"
            )

    if ctx.get("bank_accounts"):
        has_data = True
        lines.append("Bank Accounts:")
        for b in ctx["bank_accounts"]:
            lines.append(f"  {b['name']}: {b['balance']:,.2f} {b['currency']}")

    return "\n".join(lines) if has_data else ""
