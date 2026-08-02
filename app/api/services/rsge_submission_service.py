"""app/api/services/rsge_submission_service.py — RS.ge PAYG Declaration Submission.

Submits payroll PAYG XML to the Georgian Revenue Service (RS.ge) taxpayer portal.

Configuration (env vars):
  RSGE_API_URL       — RS.ge API base URL (e.g. https://taxpayer.rs.ge/api/v1)
                       Defaults to demo endpoint when not set.
  RSGE_DEMO_MODE     — Set to "true" to force demo mode even if URL is configured.

Tenant credentials are stored in the tenant_rsge_credentials table:
  username, password, taxpayer_inn

Status codes returned:
  submitted          — accepted by RS.ge, submission_ref returned
  rejected           — RS.ge refused the declaration (validation error)
  demo_submitted     — demo mode, no real submission made
  error              — network or unexpected error
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.api.db import get_conn, _q

log = logging.getLogger(__name__)

RSGE_API_URL = os.environ.get("RSGE_API_URL", "").strip()
_DEMO_MODE = os.environ.get("RSGE_DEMO_MODE", "").lower() in ("1", "true", "yes")

# RS.ge API paths (relative to RSGE_API_URL)
_PATH_SUBMIT = "/declarations/payg"
_PATH_STATUS = "/declarations/payg/{ref}/status"

_TIMEOUT_SECONDS = 30


def _is_demo() -> bool:
    return _DEMO_MODE or not RSGE_API_URL


async def _load_credentials(tenant_id: str) -> dict | None:
    """Load RS.ge credentials from DB. Returns None if not configured."""
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q(
                "SELECT username, password, taxpayer_inn "
                "FROM tenant_rsge_credentials WHERE tenant_id = %s"
            ), tenant_id)
        return dict(row) if row else None
    except Exception as exc:
        log.warning("rsge_credentials_load_failed tenant=%s error=%s", tenant_id, exc)
        return None


def _build_auth_header(username: str, password: str) -> dict:
    """Basic auth header for RS.ge API."""
    import base64
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _submission_ref_demo(tenant_id: str, run_id: int, period: str) -> str:
    """Deterministic demo reference — same input always yields same ref."""
    h = hashlib.sha256(f"{tenant_id}:{run_id}:{period}".encode()).hexdigest()[:12].upper()
    return f"DEMO-{h}"


async def submit_payg_declaration(
    tenant_id: str,
    run_id: int,
    period: str,
    xml_content: str,
) -> dict[str, Any]:
    """Submit a PAYG XML declaration to RS.ge.

    Returns:
        {
          "ok": bool,
          "mode": "live" | "demo",
          "status": "submitted" | "demo_submitted" | "rejected" | "error",
          "submission_ref": str | None,
          "submitted_at": ISO datetime string | None,
          "message": str,
          "error_detail": str | None,
        }
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    if _is_demo():
        ref = _submission_ref_demo(tenant_id, run_id, period)
        log.info(
            "rsge_submit demo tenant=%s run_id=%s period=%s ref=%s",
            tenant_id, run_id, period, ref,
        )
        return {
            "ok": True,
            "mode": "demo",
            "status": "demo_submitted",
            "submission_ref": ref,
            "submitted_at": now_iso,
            "message": f"Demo submission accepted — ref={ref}. "
                       "Set RSGE_API_URL to enable live submission.",
            "error_detail": None,
        }

    creds = await _load_credentials(tenant_id)
    if not creds:
        return {
            "ok": False,
            "mode": "live",
            "status": "error",
            "submission_ref": None,
            "submitted_at": None,
            "message": "RS.ge credentials not configured for this tenant",
            "error_detail": "No credentials found in tenant_rsge_credentials",
        }

    headers = {
        "Content-Type": "application/xml; charset=utf-8",
        "Accept": "application/json",
        "X-Taxpayer-Inn": creds.get("taxpayer_inn") or "",
        **_build_auth_header(creds["username"], creds["password"]),
    }

    url = f"{RSGE_API_URL.rstrip('/')}{_PATH_SUBMIT}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, content=xml_content.encode("utf-8"), headers=headers)

        if resp.status_code in (200, 201, 202):
            try:
                body = resp.json()
            except Exception:
                body = {}
            ref = body.get("submission_ref") or body.get("ref") or body.get("id") or f"RSGE-{run_id}"
            log.info(
                "rsge_submit_ok tenant=%s run_id=%s period=%s ref=%s status=%s",
                tenant_id, run_id, period, ref, resp.status_code,
            )
            return {
                "ok": True,
                "mode": "live",
                "status": "submitted",
                "submission_ref": str(ref),
                "submitted_at": now_iso,
                "message": f"Submission accepted by RS.ge — ref={ref}",
                "error_detail": None,
            }

        # RS.ge returned a non-2xx — treat as rejection
        try:
            err_body = resp.json()
        except Exception:
            err_body = {"raw": resp.text[:500]}

        log.warning(
            "rsge_submit_rejected tenant=%s run_id=%s period=%s status=%s body=%s",
            tenant_id, run_id, period, resp.status_code, err_body,
        )
        return {
            "ok": False,
            "mode": "live",
            "status": "rejected",
            "submission_ref": None,
            "submitted_at": None,
            "message": f"RS.ge rejected the submission (HTTP {resp.status_code})",
            "error_detail": f"RS.ge validation failed with HTTP {resp.status_code}",
        }

    except httpx.TimeoutException:
        log.error("rsge_submit_timeout tenant=%s run_id=%s url=%s", tenant_id, run_id, url)
        return {
            "ok": False,
            "mode": "live",
            "status": "error",
            "submission_ref": None,
            "submitted_at": None,
            "message": "RS.ge submission timed out",
            "error_detail": f"Timeout after {_TIMEOUT_SECONDS}s",
        }
    except Exception as exc:
        log.error("rsge_submit_error tenant=%s run_id=%s error=%s", tenant_id, run_id, exc)
        return {
            "ok": False,
            "mode": "live",
            "status": "error",
            "submission_ref": None,
            "submitted_at": None,
            "message": "RS.ge submission failed",
            "error_detail": type(exc).__name__,
        }


async def check_submission_status(
    tenant_id: str,
    submission_ref: str,
) -> dict[str, Any]:
    """Poll RS.ge for the current status of a submitted declaration."""
    if _is_demo():
        return {
            "ok": True,
            "mode": "demo",
            "submission_ref": submission_ref,
            "status": "accepted",
            "message": "Demo mode — status always accepted",
        }

    creds = await _load_credentials(tenant_id)
    if not creds:
        return {
            "ok": False,
            "status": "error",
            "message": "RS.ge credentials not configured",
        }

    headers = {
        "Accept": "application/json",
        **_build_auth_header(creds["username"], creds["password"]),
    }
    safe_ref = quote(submission_ref, safe="")
    url = f"{RSGE_API_URL.rstrip('/')}{_PATH_STATUS.format(ref=safe_ref)}"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            body = resp.json()
            return {
                "ok": True,
                "mode": "live",
                "submission_ref": submission_ref,
                "status": body.get("status", "unknown"),
                "message": body.get("message", ""),
                "raw": body,
            }
        return {
            "ok": False,
            "mode": "live",
            "submission_ref": submission_ref,
            "status": "error",
            "message": f"RS.ge returned HTTP {resp.status_code}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "mode": "live",
            "submission_ref": submission_ref,
            "status": "error",
            "message": "RS.ge status check failed",
        }
