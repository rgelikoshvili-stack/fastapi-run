"""app/api/services/reversal_service.py — Reversal and adjustment journal entry workflow (BIZ-3).

Accounting safety rules:
  - Original posted entries are NEVER modified or deleted.
  - Reversal flips every line's debit/credit; DR=CR must hold.
  - Reversal references original via reversal_of_draft_id.
  - Reversal date must be in an open period (unless admin override).
  - Adjustment is a new balanced journal entry referencing the original.
  - Both create drafts in 'pending_approval' status (normal approval flow applies).
  - Duplicate reversal protection: second reversal raises ValueError.
  - All actions emit audit events via log_event().

Entry point functions:
  create_reversal_draft(tenant_id, original_draft_id, reversal_date, reason, actor)
  create_adjustment_draft(tenant_id, original_draft_id, adj_date, reason, actor, lines)
"""
from __future__ import annotations

import json
import logging
from datetime import date as _date
from decimal import Decimal
from typing import Optional

from app.api.db import get_conn, _q
from app.api.audit_service import log_event
from app.api.services.period_lock_service import assert_period_open, PeriodLockedError
from app.api.services.posting_helpers import (
    _normalize_lines,
    _validate_lines,
    _derive_amount_from_lines,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def flip_lines(lines: list[dict]) -> list[dict]:
    """Flip debit/credit on every line. Returns a new list; original untouched."""
    result = []
    for ln in lines:
        result.append({
            **ln,
            "debit":  ln.get("credit", 0) or 0,
            "credit": ln.get("debit",  0) or 0,
        })
    return result


def lines_balanced(lines: list[dict]) -> bool:
    """Return True if sum(debit) == sum(credit) within ±0.005."""
    total_dr = sum(Decimal(str(ln.get("debit",  0) or 0)) for ln in lines)
    total_cr = sum(Decimal(str(ln.get("credit", 0) or 0)) for ln in lines)
    return abs(total_dr - total_cr) < Decimal("0.005")


async def _fetch_draft(conn, draft_id: int, tenant_id: str) -> Optional[dict]:
    row = await conn.fetchrow(
        _q("""
            SELECT id, tenant_id, date, description, partner,
                   COALESCE(amount, 0) AS amount,
                   COALESCE(currency, 'GEL') AS currency,
                   status,
                   COALESCE(lines_json, '[]'::jsonb) AS lines_json
            FROM journal_drafts
            WHERE id = %s AND tenant_id = %s
        """),
        draft_id, tenant_id,
    )
    if not row:
        return None
    return {
        "id":          row["id"],
        "tenant_id":   row["tenant_id"],
        "date":        str(row["date"]) if row["date"] else None,
        "description": row["description"],
        "partner":     row["partner"],
        "amount":      float(row["amount"] or 0),
        "currency":    row["currency"],
        "status":      row["status"],
        "lines":       _normalize_lines(row["lines_json"]),
    }


async def _reversal_already_exists(conn, original_draft_id: int, tenant_id: str) -> bool:
    """Return True if a non-rejected reversal draft for original_draft_id exists."""
    row = await conn.fetchrow(
        _q("""
            SELECT id FROM journal_drafts
            WHERE tenant_id = %s
              AND reversal_of_draft_id = %s
              AND status NOT IN ('rejected')
            LIMIT 1
        """),
        tenant_id, original_draft_id,
    )
    return row is not None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def create_reversal_draft(
    tenant_id: str,
    original_draft_id: int,
    reversal_date: str,
    reason: str,
    actor: str,
    allow_closed_period: bool = False,
) -> dict:
    """Create a reversal draft for a posted journal entry.

    The original draft is never touched.
    Returns the new reversal draft dict (status=pending_approval).
    Raises ValueError for validation errors, PeriodLockedError for locked dates.

    RBAC: caller must verify actor has approval:write permission before calling.
    """
    if not reason or not reason.strip():
        raise ValueError("reversal_reason is required and cannot be blank")

    reversal_date_obj = _date.fromisoformat(str(reversal_date)[:10])

    async with get_conn() as conn:
        # 1. Fetch and validate original
        original = await _fetch_draft(conn, original_draft_id, tenant_id)
        if not original:
            raise ValueError(
                f"draft {original_draft_id} not found for tenant {tenant_id}"
            )
        if original["status"] not in ("posted", "simulated_success"):
            raise ValueError(
                f"draft {original_draft_id} has status={original['status']}; "
                "only posted entries can be reversed"
            )

        # 2. Duplicate reversal protection
        if await _reversal_already_exists(conn, original_draft_id, tenant_id):
            raise ValueError(
                f"A non-rejected reversal for draft {original_draft_id} already exists. "
                "Post a second correcting adjustment entry instead."
            )

        # 3. Period check — reversal date must be in an open period
        if not allow_closed_period:
            await assert_period_open(conn, tenant_id, reversal_date_obj, "reversal")

        # 4. Build reversed lines
        reversed_lines = flip_lines(original["lines"])
        if not reversed_lines:
            raise ValueError(
                f"draft {original_draft_id} has no lines to reverse"
            )
        if not lines_balanced(reversed_lines):
            raise ValueError(
                "Reversed lines are not balanced — internal error. "
                "Check original entry for corrupted line data."
            )

        line_error = _validate_lines(reversed_lines)
        if line_error:
            raise ValueError(f"Reversal lines failed validation: {line_error}")

        amount = _derive_amount_from_lines(reversed_lines)
        description = f"[REVERSAL of #{original_draft_id}] {reason.strip()}"

        # 5. Insert reversal draft (pending_approval, goes through normal approval flow)
        row = await conn.fetchrow(
            _q("""
                INSERT INTO journal_drafts
                    (tenant_id, date, description, partner, amount, currency,
                     status, lines_json, reversal_of_draft_id, reversal_reason, entry_type)
                VALUES
                    (%s, %s::date, %s, %s, %s, %s,
                     'pending_approval', %s::jsonb, %s, %s, 'reversal')
                RETURNING id, tenant_id, date, description, amount, currency, status
            """),
            tenant_id,
            str(reversal_date_obj),
            description,
            original.get("partner") or "",
            amount,
            original["currency"],
            json.dumps(reversed_lines, ensure_ascii=False),
            original_draft_id,
            reason.strip(),
        )

        reversal_id = row["id"]

        # 6. Audit event
        log_event(
            "reversal_draft_created",
            {
                "entity_type":         "journal_draft",
                "entity_id":           reversal_id,
                "original_draft_id":   original_draft_id,
                "reversal_date":       str(reversal_date_obj),
                "reason":              reason.strip(),
                "actor":               actor,
                "lines_count":         len(reversed_lines),
            },
            actor=actor,
            tenant_id=tenant_id,
        )

    log.info(
        "action=reversal_created tenant=%s original_draft=%s reversal_draft=%s actor=%s",
        tenant_id, original_draft_id, reversal_id, actor,
    )

    return {
        "id":                  reversal_id,
        "tenant_id":           tenant_id,
        "date":                str(reversal_date_obj),
        "description":         description,
        "amount":              amount,
        "currency":            original["currency"],
        "status":              "pending_approval",
        "entry_type":          "reversal",
        "reversal_of_draft_id": original_draft_id,
        "reversal_reason":     reason.strip(),
        "lines":               reversed_lines,
    }


async def create_adjustment_draft(
    tenant_id: str,
    original_draft_id: int,
    adjustment_date: str,
    reason: str,
    actor: str,
    lines: list[dict],
    allow_closed_period: bool = False,
) -> dict:
    """Create an adjustment (correcting) journal entry referencing the original.

    The original draft is never touched.
    Adjustment date must be in an open period unless allow_closed_period=True.
    Lines must be DR=CR balanced and non-empty.
    Returns the new adjustment draft dict (status=pending_approval).

    RBAC: caller must verify actor has approval:write permission before calling.
    """
    if not reason or not reason.strip():
        raise ValueError("adjustment_reason is required and cannot be blank")
    if not lines:
        raise ValueError("adjustment lines are required")

    adjustment_date_obj = _date.fromisoformat(str(adjustment_date)[:10])
    normalized = _normalize_lines(lines)

    if not lines_balanced(normalized):
        raise ValueError(
            "Adjustment lines are not balanced (DR ≠ CR). "
            "Every correcting entry must have equal debits and credits."
        )

    line_error = _validate_lines(normalized)
    if line_error:
        raise ValueError(f"Adjustment lines failed validation: {line_error}")

    async with get_conn() as conn:
        # 1. Validate original exists (doesn't need to be posted for adjustment)
        original = await _fetch_draft(conn, original_draft_id, tenant_id)
        if not original:
            raise ValueError(
                f"draft {original_draft_id} not found for tenant {tenant_id}"
            )

        # 2. Period check — adjustment date must be in an open period
        if not allow_closed_period:
            await assert_period_open(conn, tenant_id, adjustment_date_obj, "adjustment")

        amount = _derive_amount_from_lines(normalized)
        description = f"[ADJUSTMENT of #{original_draft_id}] {reason.strip()}"

        # 3. Insert adjustment draft
        row = await conn.fetchrow(
            _q("""
                INSERT INTO journal_drafts
                    (tenant_id, date, description, partner, amount, currency,
                     status, lines_json, reversal_of_draft_id, reversal_reason, entry_type)
                VALUES
                    (%s, %s::date, %s, %s, %s, %s,
                     'pending_approval', %s::jsonb, %s, %s, 'adjustment')
                RETURNING id, tenant_id, date, description, amount, currency, status
            """),
            tenant_id,
            str(adjustment_date_obj),
            description,
            original.get("partner") or "",
            amount,
            original.get("currency", "GEL"),
            json.dumps(normalized, ensure_ascii=False),
            original_draft_id,
            reason.strip(),
        )

        adj_id = row["id"]

        # 4. Audit event
        log_event(
            "adjustment_draft_created",
            {
                "entity_type":       "journal_draft",
                "entity_id":         adj_id,
                "original_draft_id": original_draft_id,
                "adjustment_date":   str(adjustment_date_obj),
                "reason":            reason.strip(),
                "actor":             actor,
                "lines_count":       len(normalized),
            },
            actor=actor,
            tenant_id=tenant_id,
        )

    log.info(
        "action=adjustment_created tenant=%s original_draft=%s adj_draft=%s actor=%s",
        tenant_id, original_draft_id, adj_id, actor,
    )

    return {
        "id":                  adj_id,
        "tenant_id":           tenant_id,
        "date":                str(adjustment_date_obj),
        "description":         description,
        "amount":              amount,
        "currency":            original.get("currency", "GEL"),
        "status":              "pending_approval",
        "entry_type":          "adjustment",
        "adjusts_draft_id":    original_draft_id,
        "adjustment_reason":   reason.strip(),
        "lines":               normalized,
    }
