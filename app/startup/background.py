"""app/startup/background.py — Supervised background task loops."""
import asyncio
import logging
from app.api.metrics import WORKER_ERRORS
from app.api.db import get_conn, _q

_TASK_MAX_FAILURES = 5


async def _monitored_loop(name: str, fn, interval: int, max_failures: int = _TASK_MAX_FAILURES):
    """
    Generic supervisor for background loops.
    Tracks consecutive failures; backs off to interval*10 after max_failures.
    Always resumes — never crashes the app.
    """
    log = logging.getLogger(f"bg.{name}")
    consecutive_failures = 0

    while True:
        try:
            result = await fn()
            if consecutive_failures > 0:
                log.info("task=%s recovered after %d failures result=%s", name, consecutive_failures, result)
            consecutive_failures = 0
            sleep_for = interval
        except Exception as exc:
            consecutive_failures += 1
            WORKER_ERRORS.labels(worker=name).inc()
            if consecutive_failures >= max_failures:
                log.error(
                    "task=%s REPEATED_FAILURE consecutive=%d error=%s — backing off %ds",
                    name, consecutive_failures, exc, interval * 10,
                    exc_info=True,
                )
                sleep_for = interval * 10
            else:
                log.warning("task=%s failure=%d/%d error=%s", name, consecutive_failures, max_failures, exc)
                sleep_for = interval

        await asyncio.sleep(sleep_for)


async def _get_active_tenant_ids() -> list[str]:
    """Return all non-inactive tenant IDs from the tenants table."""
    _log = logging.getLogger("bg.autopilot")
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(
                "SELECT tenant_id FROM tenants "
                "WHERE status IS NULL OR status NOT IN ('inactive', 'suspended')"
            )
        ids = [r["tenant_id"] for r in rows]
        return ids if ids else ["default"]
    except Exception as exc:
        _log.warning(
            "task=autopilot _get_active_tenant_ids failed: %s — falling back to ['default']",
            exc,
        )
        return ["default"]


async def autopilot_loop():
    from app.api.services.approval_service import autopilot_approve_service
    log = logging.getLogger("bg.autopilot")

    async def _run():
        loop = asyncio.get_running_loop()
        tenant_ids = await _get_active_tenant_ids()
        log.info("task=autopilot starting tenants=%d", len(tenant_ids))
        total_approved = 0
        for tenant_id in tenant_ids:
            try:
                result = await loop.run_in_executor(
                    None, lambda t=tenant_id: autopilot_approve_service(t)
                )
                approved = result.get("approved", 0) if isinstance(result, dict) else 0
                total_approved += approved
                if approved:
                    log.info("task=autopilot tenant=%s approved=%d", tenant_id, approved)
            except Exception as exc:
                log.warning("task=autopilot tenant=%s error=%s", tenant_id, exc)
        log.info(
            "task=autopilot done total_approved=%d tenants=%d",
            total_approved,
            len(tenant_ids),
        )
        return {"total_approved": total_approved, "tenants": len(tenant_ids)}

    await _monitored_loop("autopilot", _run, interval=60)


async def decay_loop():
    from app.api.services.learning_service import run_decay_service
    log = logging.getLogger("bg.decay")

    async def _run():
        log.info("task=decay running")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, run_decay_service)
        log.info("task=decay result=%s", result)
        return result

    await _monitored_loop("decay", _run, interval=3600)


async def email_poller_loop():
    """Poll all active tenants' inboxes every 5 minutes."""
    from app.api.services.email_collector import collect_tenant_inbox, get_all_active_tenants
    log = logging.getLogger("bg.email_poller")
    await asyncio.sleep(30)  # warm-up

    async def _run():
        import asyncio as _asyncio
        tenants = await get_all_active_tenants()
        total_processed = 0
        loop = _asyncio.get_running_loop()
        for tid in tenants:
            try:
                # run_in_executor prevents blocking IMAP calls from stalling the event loop
                result = await _asyncio.wait_for(
                    loop.run_in_executor(None, lambda t=tid: _asyncio.run(collect_tenant_inbox(t))),
                    timeout=20.0,
                )
                processed = result.get("processed", 0)
                total_processed += processed
                if processed > 0:
                    log.info("task=email_poller tenant=%s drafted=%d", tid, processed)
            except _asyncio.TimeoutError:
                log.warning("task=email_poller tenant=%s timeout after 20s", tid)
            except Exception as e:
                log.warning("task=email_poller tenant=%s error=%s", tid, e)
        return {"total_processed": total_processed, "tenants": len(tenants)}

    await _monitored_loop("email_poller", _run, interval=300)
