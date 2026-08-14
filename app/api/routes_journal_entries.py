"""app/api/routes_journal_entries.py — Journal entry reversal and adjustment routes (BIZ-3).

Endpoints:
  POST /api/journal-entries/{draft_id}/reverse
  POST /api/journal-entries/{draft_id}/adjust

Both endpoints:
  - Require approval:write permission
  - Validate actor via request.state
  - Call reversal_service or adjustment_service
  - Return ok_response / error_response envelope
  - Never modify the original posted entry
"""
import logging
from typing import Optional

from fastapi import APIRouter, Request

from app.api.authz import require_permission
from app.api.response_utils import ok_response, error_response
from app.api.tenant_context import resolve_tenant_id
from app.api.services.period_lock_service import PeriodLockedError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/journal-entries", tags=["journal-entries"])


@router.post("/{draft_id}/reverse")
async def reverse_journal_entry(draft_id: int, request: Request, payload: dict):
    """Create a reversal draft for a posted journal entry.

    Body:
      reversal_date  (str, YYYY-MM-DD, required)
      reason         (str, required)
      allow_closed_period (bool, optional — admin override, defaults False)

    Original entry is never modified. Reversal goes through normal approval flow.
    Permission: approval:write
    """
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor     = getattr(request.state, "user_email", None) or getattr(request.state, "user_id", "system")

    reversal_date = payload.get("reversal_date")
    reason        = str(payload.get("reason") or "").strip()
    allow_closed  = bool(payload.get("allow_closed_period", False))

    if not reversal_date:
        return error_response("reversal_date is required", "VALIDATION_ERROR")
    if not reason:
        return error_response("reason is required and cannot be blank", "VALIDATION_ERROR")

    try:
        from app.api.services.reversal_service import create_reversal_draft
        result = await create_reversal_draft(
            tenant_id=tenant_id,
            original_draft_id=draft_id,
            reversal_date=reversal_date,
            reason=reason,
            actor=actor,
            allow_closed_period=allow_closed,
        )
        return ok_response(
            f"Reversal draft #{result['id']} created for entry #{draft_id}. "
            "Awaiting approval before posting.",
            result,
        )
    except PeriodLockedError as e:
        return error_response(str(e), "PERIOD_LOCKED", {"draft_id": draft_id})
    except ValueError as e:
        return error_response(str(e), "VALIDATION_ERROR", {"draft_id": draft_id})
    except Exception as e:
        log.error("reverse_journal_entry failed draft_id=%s: %s", draft_id, e)
        return error_response("Reversal failed", "REVERSAL_ERROR", str(e))


@router.post("/{draft_id}/adjust")
async def adjust_journal_entry(draft_id: int, request: Request, payload: dict):
    """Create an adjustment (correcting) journal entry referencing a posted entry.

    Body:
      adjustment_date  (str, YYYY-MM-DD, required)
      reason           (str, required)
      lines            (list, required — balanced DR=CR journal lines)
      allow_closed_period (bool, optional — admin override, defaults False)

    Original entry is never modified. Adjustment goes through normal approval flow.
    Permission: approval:write
    """
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor     = getattr(request.state, "user_email", None) or getattr(request.state, "user_id", "system")

    adjustment_date = payload.get("adjustment_date")
    reason          = str(payload.get("reason") or "").strip()
    lines           = payload.get("lines") or []
    allow_closed    = bool(payload.get("allow_closed_period", False))

    if not adjustment_date:
        return error_response("adjustment_date is required", "VALIDATION_ERROR")
    if not reason:
        return error_response("reason is required and cannot be blank", "VALIDATION_ERROR")
    if not lines:
        return error_response("lines are required for an adjustment entry", "VALIDATION_ERROR")

    try:
        from app.api.services.reversal_service import create_adjustment_draft
        result = await create_adjustment_draft(
            tenant_id=tenant_id,
            original_draft_id=draft_id,
            adjustment_date=adjustment_date,
            reason=reason,
            actor=actor,
            lines=lines,
            allow_closed_period=allow_closed,
        )
        return ok_response(
            f"Adjustment draft #{result['id']} created for entry #{draft_id}. "
            "Awaiting approval before posting.",
            result,
        )
    except PeriodLockedError as e:
        return error_response(str(e), "PERIOD_LOCKED", {"draft_id": draft_id})
    except ValueError as e:
        return error_response(str(e), "VALIDATION_ERROR", {"draft_id": draft_id})
    except Exception as e:
        log.error("adjust_journal_entry failed draft_id=%s: %s", draft_id, e)
        return error_response("Adjustment failed", "ADJUSTMENT_ERROR", str(e))
