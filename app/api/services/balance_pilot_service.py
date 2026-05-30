"""app/api/services/balance_pilot_service.py — Balance.ge Controlled Pilot (Phase 4).

Manages the explicit sign-off workflow before enabling live Balance.ge posting
for a specific tenant.

Workflow:
  1. run_preflight_check  — verify all prerequisites are met
  2. enable_live_posting  — admin sign-off; sets per-tenant flag
  3. disable_live_posting — emergency disable (rollback)
  4. get_pilot_status     — current state + preflight summary

Per-tenant flag stored in tenant_settings: "balance.live_posting_enabled" = true/false
Sign-off record stored in:             "balance.pilot_signoff" = {actor, timestamp, ...}

IMPORTANT: even when per-tenant flag is set, the global env var
POSTED_LEDGER_WRITES_ENABLED must also be "true" for live posting to occur.
This double-gate is intentional.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.api.db import get_conn, _q
from app.api.services.tenant_config_service import get_tenant_setting, set_tenant_setting

BALANCE_LIVE_KEY   = "balance.live_posting_enabled"
BALANCE_SIGNOFF_KEY = "balance.pilot_signoff"


# ---------------------------------------------------------------------------
# Preflight checks (pure + async)
# ---------------------------------------------------------------------------

def _preflight_result(name: str, passed: bool, detail: str) -> dict:
    return {"check": name, "passed": passed, "detail": detail}


async def run_preflight_check(tenant_id: str) -> dict[str, Any]:
    """Run all prerequisite checks before enabling live Balance.ge posting.

    Returns:
        {"ready": bool, "checks": [...], "blockers": [...]}
    """
    checks = []
    blockers = []

    # 1. dry_run has been executed at least once
    async with get_conn() as conn:
        dry_run_count = await conn.fetchval(
            _q("""
                SELECT COUNT(*) FROM posting_log
                WHERE tenant_id = $1 AND target_system = 'balance'
                  AND status = 'dry_run'
            """),
            tenant_id,
        )
        # 2. Balance credentials in vault (not plaintext)
        cred_row = await conn.fetchrow(
            _q("""
                SELECT id, masked_hint FROM balance_credentials
                WHERE tenant_id = $1
                LIMIT 1
            """),
            tenant_id,
        )
        # 3. At least one approved draft exists (approval workflow active)
        approved_count = await conn.fetchval(
            _q("""
                SELECT COUNT(*) FROM journal_drafts
                WHERE tenant_id = $1 AND status = 'approved'
            """),
            tenant_id,
        )

    # Check 1: dry_run
    dr_ok = int(dry_run_count or 0) > 0
    checks.append(_preflight_result(
        "dry_run_executed",
        dr_ok,
        f"{dry_run_count} dry-run(s) on Balance connector" if dr_ok
        else "Run POST /posting/balance/dry-run/{draft_id} first",
    ))
    if not dr_ok:
        blockers.append("dry_run_executed")

    # Check 2: credentials in vault
    cred_ok = cred_row is not None
    checks.append(_preflight_result(
        "credentials_configured",
        cred_ok,
        f"Balance credentials found (masked: {cred_row['masked_hint']})" if cred_ok
        else "No Balance.ge credentials found — add via /vault/credentials",
    ))
    if not cred_ok:
        blockers.append("credentials_configured")

    # Check 3: approval workflow active
    appr_ok = int(approved_count or 0) > 0
    checks.append(_preflight_result(
        "approval_workflow_active",
        appr_ok,
        f"{approved_count} approved draft(s) confirm approval workflow is active" if appr_ok
        else "No approved drafts found — test approval workflow first",
    ))
    if not appr_ok:
        blockers.append("approval_workflow_active")

    return {
        "tenant_id": tenant_id,
        "ready":     len(blockers) == 0,
        "checks":    checks,
        "blockers":  blockers,
    }


# ---------------------------------------------------------------------------
# Pilot enable / disable
# ---------------------------------------------------------------------------

async def enable_live_posting(
    tenant_id: str,
    signed_by: str,
    note: str = "",
) -> dict[str, Any]:
    """Enable live Balance.ge posting for *tenant_id*.

    Records the sign-off in tenant_settings. Does NOT bypass the global
    POSTED_LEDGER_WRITES_ENABLED env var — both gates must be open.

    Raises ValueError if preflight checks fail.
    """
    preflight = await run_preflight_check(tenant_id)
    if not preflight["ready"]:
        raise ValueError(f"PREFLIGHT_FAILED: {preflight['blockers']}")

    signoff = {
        "signed_by":   signed_by,
        "signed_at":   datetime.now(tz=timezone.utc).isoformat(),
        "note":        note,
        "preflight":   preflight["checks"],
    }
    await set_tenant_setting(tenant_id, BALANCE_LIVE_KEY,   True)
    await set_tenant_setting(tenant_id, BALANCE_SIGNOFF_KEY, signoff)

    return {
        "tenant_id": tenant_id,
        "enabled":   True,
        "signed_by": signed_by,
        "warning":   (
            "Live posting is now ENABLED for this tenant. "
            "The global POSTED_LEDGER_WRITES_ENABLED env var must also be 'true' "
            "for actual ERP calls to proceed."
        ),
    }


async def disable_live_posting(
    tenant_id: str,
    disabled_by: str,
    reason: str = "",
) -> dict[str, Any]:
    """Emergency disable of live Balance.ge posting for *tenant_id*."""
    await set_tenant_setting(tenant_id, BALANCE_LIVE_KEY, False)
    await set_tenant_setting(tenant_id, "balance.pilot_disable_log", {
        "disabled_by": disabled_by,
        "disabled_at": datetime.now(tz=timezone.utc).isoformat(),
        "reason":      reason,
    })
    return {
        "tenant_id": tenant_id,
        "enabled":   False,
        "disabled_by": disabled_by,
        "reason":    reason,
    }


async def get_pilot_status(tenant_id: str) -> dict[str, Any]:
    """Return current pilot status + sign-off record for *tenant_id*."""
    enabled = await get_tenant_setting(tenant_id, BALANCE_LIVE_KEY, False)
    signoff  = await get_tenant_setting(tenant_id, BALANCE_SIGNOFF_KEY, None)
    disable_log = await get_tenant_setting(tenant_id, "balance.pilot_disable_log", None)

    import os
    global_gate = os.environ.get("POSTED_LEDGER_WRITES_ENABLED", "false").lower() == "true"

    return {
        "tenant_id":          tenant_id,
        "tenant_enabled":     bool(enabled),
        "global_gate_open":   global_gate,
        "live_posting_active": bool(enabled) and global_gate,
        "signoff":            signoff,
        "disable_log":        disable_log,
    }
