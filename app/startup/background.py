"""app/startup/background.py — Supervised background task loops."""
import asyncio
import logging

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


async def autopilot_loop():
    from app.api.services.approval_service import autopilot_approve_service
    log = logging.getLogger("bg.autopilot")

    async def _run():
        log.info("task=autopilot running")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: autopilot_approve_service("default"))
        log.info("task=autopilot approved=%s", result)
        return result

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
        tenants = get_all_active_tenants()
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
