"""P1 regression tests for the email poller's event-loop boundary."""
from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from unittest.mock import AsyncMock, patch

import pytest


async def _capture_poller_run(tenant_ids, collect):
    captured = {}

    async def _capture(name, fn, interval):
        captured["name"] = name
        captured["fn"] = fn
        captured["interval"] = interval

    with patch("app.startup.background._monitored_loop", side_effect=_capture), \
         patch("app.startup.background.asyncio.sleep", new=AsyncMock()), \
         patch(
             "app.api.services.email_collector.get_all_active_tenants",
             new=AsyncMock(return_value=tenant_ids),
         ), \
         patch(
             "app.api.services.email_collector.collect_tenant_inbox",
             side_effect=collect,
         ):
        from app.startup.background import email_poller_loop

        await email_poller_loop()

    return captured["fn"]


def test_email_poller_does_not_call_asyncio_run():
    from app.startup import background

    source = inspect.getsource(background.email_poller_loop)
    assert "asyncio.run(" not in source
    assert "_asyncio.run(" not in source


def test_email_poller_does_not_submit_collector_to_executor():
    from app.startup import background

    source = inspect.getsource(background.email_poller_loop)
    assert "run_in_executor" not in source
    assert "run_email_tenant_work(" in source
    assert "collect_tenant_inbox(trusted_tid)" in source


@pytest.mark.asyncio
async def test_collect_tenant_inbox_awaited_on_running_loop():
    running_loop = asyncio.get_running_loop()
    calls = []

    async def collect(tenant_id):
        calls.append((tenant_id, asyncio.get_running_loop(), threading.current_thread()))
        return {"processed": 1}

    run = await _capture_poller_run(["tenant-a"], collect)
    result = await run()

    assert result == {"total_processed": 1, "tenants": 1}
    assert calls[0][0] == "tenant-a"
    assert calls[0][1] is running_loop
    assert calls[0][2] is threading.current_thread()


@pytest.mark.asyncio
async def test_timeout_on_one_tenant_does_not_stop_others():
    processed = []

    async def collect(tenant_id):
        if tenant_id == "slow":
            await asyncio.sleep(60)
        processed.append(tenant_id)
        return {"processed": 1}

    wait_call = 0

    async def fast_wait_for(awaitable, timeout):
        nonlocal wait_call
        wait_call += 1
        if wait_call == 2:
            awaitable.close()
            raise asyncio.TimeoutError
        return await awaitable

    run = await _capture_poller_run(["good-1", "slow", "good-2"], collect)
    with patch("app.startup.background.asyncio.wait_for", side_effect=fast_wait_for):
        result = await run()

    assert processed == ["good-1", "good-2"]
    assert result == {"total_processed": 2, "tenants": 3}


@pytest.mark.asyncio
async def test_exception_on_one_tenant_does_not_stop_others():
    processed = []

    async def collect(tenant_id):
        if tenant_id == "bad":
            raise RuntimeError("mailbox unavailable")
        processed.append(tenant_id)
        return {"processed": 1}

    run = await _capture_poller_run(["good-1", "bad", "good-2"], collect)
    result = await run()

    assert processed == ["good-1", "good-2"]
    assert result == {"total_processed": 2, "tenants": 3}


@pytest.mark.asyncio
async def test_empty_tenant_list_is_clean_noop():
    collect = AsyncMock(return_value={"processed": 1})
    run = await _capture_poller_run([], collect)

    assert await run() == {"total_processed": 0, "tenants": 0}
    collect.assert_not_awaited()


@pytest.mark.asyncio
async def test_failure_log_includes_tenant_id(caplog):
    async def collect(_tenant_id):
        raise RuntimeError("mailbox unavailable")

    run = await _capture_poller_run(["tenant-failed"], collect)
    with caplog.at_level(logging.WARNING, logger="bg.email_poller"):
        await run()

    assert "tenant=tenant-failed" in caplog.text
    assert "error=mailbox unavailable" in caplog.text


@pytest.mark.asyncio
async def test_timeout_log_includes_tenant_id(caplog):
    async def collect(_tenant_id):
        return {"processed": 0}

    async def timeout(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    run = await _capture_poller_run(["tenant-slow"], collect)
    with patch("app.startup.background.asyncio.wait_for", side_effect=timeout), \
         caplog.at_level(logging.WARNING, logger="bg.email_poller"):
        await run()

    assert "tenant=tenant-slow" in caplog.text
    assert "timeout after 20s" in caplog.text


@pytest.mark.asyncio
async def test_credential_db_lookup_stays_on_main_event_loop():
    from app.api.services import email_collector
    from app.api.db import tenant_db_context

    running_loop = asyncio.get_running_loop()
    main_thread = threading.current_thread()
    observed = {}

    async def credentials(tenant_id):
        observed["tenant_id"] = tenant_id
        observed["loop"] = asyncio.get_running_loop()
        observed["thread"] = threading.current_thread()
        return None

    with patch.object(email_collector, "get_tenant_email_credentials", side_effect=credentials):
        async with tenant_db_context("tenant-db"):
            result = await email_collector.collect_tenant_inbox("tenant-db")

    assert result["status"] == "no_credentials"
    assert observed == {
        "tenant_id": "tenant-db",
        "loop": running_loop,
        "thread": main_thread,
    }


def test_only_blocking_imap_calls_use_to_thread():
    from app.api.services import email_collector

    source = inspect.getsource(email_collector.collect_tenant_inbox)
    compact_source = "".join(source.split())
    assert "asyncio.to_thread(_imap_connect" in compact_source
    assert "asyncio.to_thread(_imap_search_unseen" in compact_source
    assert "asyncio.to_thread(_imap_fetch_raw" in compact_source
    assert "asyncio.to_thread(_imap_mark_seen" in compact_source
    assert "asyncio.to_thread(_imap_logout" in compact_source
    assert "get_conn" not in source
    assert "run_in_executor" not in source
    assert "asyncio.run(" not in source


def test_no_whole_collector_thread_leak_pattern():
    from app.startup import background

    source = inspect.getsource(background.email_poller_loop)
    forbidden = (
        "run_in_executor(None, lambda t=tid",
        "asyncio.run(collect_tenant_inbox",
        "_asyncio.run(collect_tenant_inbox",
    )
    assert all(pattern not in source for pattern in forbidden)
