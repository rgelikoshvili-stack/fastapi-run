"""app/api/services/approval_cockpit_service.py — Approval Cockpit 2.0 (Task 16 / Phase 5).

Adds to the approval workflow:
  - SLA / overdue tracking        — flag drafts waiting longer than sla_hours
  - Priority queue                — high/normal/low priority labels
  - Draft delegation              — assign draft to specific approver
  - Comment thread                — discussion notes per draft
  - Risk badges                   — HIGH/MEDIUM/LOW per draft (amount + confidence)
  - AI explanation panel          — human-readable classification reason per draft
  - Bulk approve with audit       — approve multiple drafts in one call
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.api.db import get_conn, _q

DEFAULT_SLA_HOURS = 48
PRIORITY_VALUES   = {"high", "normal", "low"}

# Risk badge thresholds (mirrors approval_service constants)
_HIGH_RISK_AMOUNT     = 1000.0
_LOW_RISK_AMOUNT      = 50.0
_HIGH_CONF_THRESHOLD  = 0.75
_LOW_CONF_THRESHOLD   = 0.50


# ---------------------------------------------------------------------------
# Risk badge + explanation (pure helpers)
# ---------------------------------------------------------------------------

def compute_risk_badge(amount: float, confidence: float | None) -> str:
    """Return 'HIGH', 'MEDIUM', or 'LOW' risk badge for a draft.

    HIGH:   large amount (>1000 GEL) OR very low confidence (<0.50)
    MEDIUM: mid-range amount (50-1000) OR moderate confidence (0.50-0.75)
    LOW:    small amount (<50 GEL) AND high confidence (>=0.75)
    """
    conf = float(confidence or 0)
    if amount > _HIGH_RISK_AMOUNT or conf < _LOW_CONF_THRESHOLD:
        return "HIGH"
    if amount < _LOW_RISK_AMOUNT and conf >= _HIGH_CONF_THRESHOLD:
        return "LOW"
    return "MEDIUM"


def build_draft_explanation(draft: dict) -> str:
    """Return a human-readable AI explanation for a draft's classification."""
    try:
        from app.api.services.classification_explanation_service import build_explanation
        result = {
            "account": draft.get("account_code", ""),
            "confidence": draft.get("confidence", 0),
            "matched_on": draft.get("description", ""),
            "source": draft.get("provider_type", "rules"),
        }
        enriched = build_explanation(result)
        return enriched.get("explanation", "")
    except Exception:
        conf = draft.get("confidence") or 0
        return f"Confidence: {int(float(conf) * 100)}%"


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def compute_sla_status(created_at_iso: str, sla_hours: int = DEFAULT_SLA_HOURS) -> dict[str, Any]:
    """Return SLA status for a draft given its creation timestamp.

    Returns:
        {"sla_hours": int, "hours_waiting": float, "overdue": bool, "urgency": str}
    urgency: "ok" | "warning" (>50% of SLA) | "overdue"
    """
    try:
        if isinstance(created_at_iso, str):
            created_at = datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
        else:
            created_at = created_at_iso
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        hours_waiting = (now - created_at).total_seconds() / 3600
    except Exception:
        return {"sla_hours": sla_hours, "hours_waiting": 0.0, "overdue": False, "urgency": "ok"}

    overdue = hours_waiting > sla_hours
    if overdue:
        urgency = "overdue"
    elif hours_waiting > sla_hours * 0.5:
        urgency = "warning"
    else:
        urgency = "ok"

    return {
        "sla_hours":     sla_hours,
        "hours_waiting": round(hours_waiting, 2),
        "overdue":       overdue,
        "urgency":       urgency,
    }


def prioritise_queue(drafts: list[dict], sla_hours: int = DEFAULT_SLA_HOURS) -> list[dict]:
    """Re-order drafts: high priority first, then by SLA urgency, then by amount desc."""
    priority_order = {"high": 0, "normal": 1, "low": 2}
    urgency_order  = {"overdue": 0, "warning": 1, "ok": 2}

    def _sort_key(d: dict):
        p = priority_order.get(d.get("priority", "normal"), 1)
        sla = compute_sla_status(str(d.get("created_at", "")), sla_hours)
        u = urgency_order.get(sla["urgency"], 2)
        amt = -float(d.get("amount") or 0)
        return (p, u, amt)

    return sorted(drafts, key=_sort_key)


# ---------------------------------------------------------------------------
# Async service functions
# ---------------------------------------------------------------------------

async def get_cockpit_queue(
    tenant_id: str,
    status: str = "drafted",
    sla_hours: int = DEFAULT_SLA_HOURS,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Return the approval queue enriched with SLA status and priority."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            _q("""
                SELECT id, description, amount, status, partner,
                       created_at, assigned_to, priority,
                       confidence, account_code, provider_type
                FROM journal_drafts
                WHERE tenant_id = $1 AND status = $2
                ORDER BY created_at ASC
                LIMIT $3 OFFSET $4
            """),
            tenant_id, status, limit, offset,
        )
        total = await conn.fetchval(
            _q("SELECT COUNT(*) FROM journal_drafts WHERE tenant_id = $1 AND status = $2"),
            tenant_id, status,
        )

    drafts = []
    overdue_count = 0
    for r in rows:
        d = dict(r)
        sla = compute_sla_status(str(d.get("created_at", "")), sla_hours)
        d["sla"] = sla
        if sla["overdue"]:
            overdue_count += 1
        if not d.get("priority"):
            d["priority"] = "normal"
        # Enrich with risk badge and AI explanation
        d["risk_badge"]   = compute_risk_badge(float(d.get("amount") or 0), d.get("confidence"))
        d["explanation"]  = build_draft_explanation(d)
        drafts.append(d)

    prioritised = prioritise_queue(drafts, sla_hours)
    return {
        "drafts":        prioritised,
        "total":         int(total or 0),
        "overdue_count": overdue_count,
        "sla_hours":     sla_hours,
    }


async def set_priority(
    tenant_id: str,
    draft_id: int,
    priority: str,
) -> dict[str, Any]:
    """Set priority for a draft. *priority* must be high/normal/low."""
    if priority not in PRIORITY_VALUES:
        raise ValueError(f"INVALID_PRIORITY: must be one of {sorted(PRIORITY_VALUES)}")
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""
                UPDATE journal_drafts
                SET priority   = $3,
                    updated_at = NOW()
                WHERE id = $1 AND tenant_id = $2
                RETURNING id, description, status, priority, updated_at
            """),
            draft_id, tenant_id, priority,
        )
    if not row:
        raise ValueError("DRAFT_NOT_FOUND")
    return dict(row)


async def delegate_draft(
    tenant_id: str,
    draft_id: int,
    assigned_to: str,
    delegated_by: str,
) -> dict[str, Any]:
    """Assign *draft_id* to *assigned_to* user."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""
                UPDATE journal_drafts
                SET assigned_to  = $3,
                    delegated_by = $4,
                    updated_at   = NOW()
                WHERE id = $1 AND tenant_id = $2
                  AND status IN ('drafted','awaiting_cfo','pending_approval')
                RETURNING id, description, status, assigned_to, delegated_by, updated_at
            """),
            draft_id, tenant_id, assigned_to, delegated_by,
        )
    if not row:
        raise ValueError("DRAFT_NOT_FOUND_OR_WRONG_STATUS")
    return dict(row)


async def add_comment(
    tenant_id: str,
    draft_id: int,
    author: str,
    body: str,
) -> dict[str, Any]:
    """Append a comment to the draft's comment thread."""
    async with get_conn() as conn:
        draft = await conn.fetchrow(
            _q("SELECT id FROM journal_drafts WHERE id = $1 AND tenant_id = $2"),
            draft_id, tenant_id,
        )
        if not draft:
            raise ValueError("DRAFT_NOT_FOUND")

        row = await conn.fetchrow(
            _q("""
                INSERT INTO draft_comments (tenant_id, draft_id, author, body)
                VALUES ($1, $2, $3, $4)
                RETURNING id, tenant_id, draft_id, author, body, created_at
            """),
            tenant_id, draft_id, author, body,
        )
    return dict(row)


async def list_comments(
    tenant_id: str,
    draft_id: int,
) -> list[dict[str, Any]]:
    """Return all comments for a draft, oldest first."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            _q("""
                SELECT id, draft_id, author, body, created_at
                FROM draft_comments
                WHERE tenant_id = $1 AND draft_id = $2
                ORDER BY created_at ASC
            """),
            tenant_id, draft_id,
        )
    return [dict(r) for r in rows]


async def get_overdue_summary(
    tenant_id: str,
    sla_hours: int = DEFAULT_SLA_HOURS,
) -> dict[str, Any]:
    """Return count and total amount of overdue drafts."""
    cutoff_interval = f"{sla_hours} hours"
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""
                SELECT
                    COUNT(*)             AS overdue_count,
                    COALESCE(SUM(amount), 0) AS overdue_amount
                FROM journal_drafts
                WHERE tenant_id = $1
                  AND status IN ('drafted', 'awaiting_cfo', 'pending_approval')
                  AND created_at < NOW() - $2::interval
            """),
            tenant_id, cutoff_interval,
        )
    return {
        "sla_hours":      sla_hours,
        "overdue_count":  int(row["overdue_count"]),
        "overdue_amount": round(float(row["overdue_amount"]), 2),
    }


async def bulk_approve(
    tenant_id: str,
    draft_ids: list[int],
    actor: str,
    note: str = "",
) -> dict[str, Any]:
    """Approve multiple drafts in one call with individual audit trail.

    Returns:
        {"approved": [...], "skipped": [...], "failed": [...]}
    Each entry: {"draft_id": int, "reason": str}
    """
    from app.api.services.approval_service import approve_draft_service

    approved = []
    skipped  = []
    failed   = []

    for draft_id in draft_ids:
        try:
            result = await approve_draft_service(draft_id, tenant_id)
            if result.get("ok"):
                approved.append({"draft_id": draft_id})
            else:
                code = (result.get("error") or {}).get("code", "UNKNOWN")
                skipped.append({"draft_id": draft_id, "reason": code})
        except Exception as exc:
            failed.append({"draft_id": draft_id, "reason": str(exc)[:80]})

    return {
        "requested":      len(draft_ids),
        "approved_count": len(approved),
        "skipped_count":  len(skipped),
        "failed_count":   len(failed),
        "approved":       approved,
        "skipped":        skipped,
        "failed":         failed,
        "actor":          actor,
        "note":           note,
    }
