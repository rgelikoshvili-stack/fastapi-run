import inspect
from unittest.mock import AsyncMock, patch

import pytest

from app.api.db import require_current_tenant_id
from app.startup import background


async def _run_one_tick(tenants, work, *, ticks=1):
    summaries = []

    async def fake_monitored(_name, fn, interval, **_kwargs):
        assert interval == 3600
        for _ in range(ticks):
            summaries.append(await fn())

    with (
        patch.object(background, "_get_active_tenant_ids", new=AsyncMock(return_value=tenants)),
        patch("app.api.services.learning_service.run_decay_service", new=work),
        patch.object(background, "_monitored_loop", new=fake_monitored),
    ):
        await background.decay_loop()
    return summaries


@pytest.mark.asyncio
async def test_each_authoritative_tenant_gets_matching_thread_context(monkeypatch):
    monkeypatch.delenv("LEARNING_DECAY_ENABLED", raising=False)
    seen = []

    def work(tenant_id):
        seen.append((tenant_id, require_current_tenant_id(tenant_id)))
        return {"ok": True, "tenant_id": tenant_id, "decayed": {"decayed": 1}}

    summaries = await _run_one_tick(["tenant-a", "tenant-b"], work)
    assert seen == [("tenant-a", "tenant-a"), ("tenant-b", "tenant-b")]
    assert summaries == [{"total_decayed": 2, "tenants": 2, "failed": 0}]
    with pytest.raises(ValueError, match="context is required"):
        require_current_tenant_id()


@pytest.mark.asyncio
async def test_tenant_failure_clears_context_before_next_tenant(monkeypatch):
    monkeypatch.delenv("LEARNING_DECAY_ENABLED", raising=False)
    seen = []

    def work(tenant_id):
        seen.append(require_current_tenant_id(tenant_id))
        if tenant_id == "tenant-a":
            raise RuntimeError("synthetic tenant failure")
        return {"ok": True, "decayed": {"decayed": 3}}

    summaries = await _run_one_tick(["tenant-a", "tenant-b"], work)
    assert seen == ["tenant-a", "tenant-b"]
    assert summaries == [{"total_decayed": 3, "tenants": 2, "failed": 1}]
    with pytest.raises(ValueError, match="context is required"):
        require_current_tenant_id()


@pytest.mark.asyncio
async def test_service_reported_failure_is_counted_and_next_tenant_runs(monkeypatch):
    monkeypatch.delenv("LEARNING_DECAY_ENABLED", raising=False)
    seen = []

    def work(tenant_id):
        seen.append(require_current_tenant_id(tenant_id))
        if tenant_id == "tenant-a":
            return {"ok": False, "error": "synthetic database failure"}
        return {"ok": True, "decayed": {"decayed": 2}}

    summaries = await _run_one_tick(["tenant-a", "tenant-b"], work)
    assert seen == ["tenant-a", "tenant-b"]
    assert summaries == [{"total_decayed": 2, "tenants": 2, "failed": 1}]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [None, "", " ", "default", " DEFAULT "])
async def test_invalid_or_default_tenant_never_reaches_decay_work(monkeypatch, invalid):
    monkeypatch.delenv("LEARNING_DECAY_ENABLED", raising=False)
    work = AsyncMock()
    summaries = await _run_one_tick([invalid], work)
    work.assert_not_awaited()
    assert summaries == [{"total_decayed": 0, "tenants": 1, "failed": 1}]


@pytest.mark.asyncio
async def test_no_tenants_means_no_business_work(monkeypatch):
    monkeypatch.delenv("LEARNING_DECAY_ENABLED", raising=False)
    work = AsyncMock()
    assert await _run_one_tick([], work) == [{"total_decayed": 0, "tenants": 0, "failed": 0}]
    work.assert_not_awaited()


@pytest.mark.asyncio
async def test_repeated_ticks_remain_tenant_scoped(monkeypatch):
    monkeypatch.delenv("LEARNING_DECAY_ENABLED", raising=False)
    seen = []

    def work(tenant_id):
        seen.append(require_current_tenant_id(tenant_id))
        return {"decayed": {"decayed": 0}}

    await _run_one_tick(["tenant-a", "tenant-b"], work, ticks=2)
    assert seen == ["tenant-a", "tenant-b", "tenant-a", "tenant-b"]


@pytest.mark.asyncio
async def test_disable_switch_stops_only_decay_scheduler(monkeypatch):
    monkeypatch.setenv("LEARNING_DECAY_ENABLED", "false")
    with (
        patch.object(background, "_get_active_tenant_ids", new=AsyncMock()) as enumerate_tenants,
        patch.object(background, "_monitored_loop", new=AsyncMock()) as monitored,
    ):
        await background.decay_loop()
    enumerate_tenants.assert_not_awaited()
    monitored.assert_not_awaited()


def test_scheduler_has_no_unscoped_or_default_decay_call():
    source = inspect.getsource(background.decay_loop)
    assert "run_in_executor(None, run_decay_service)" not in source
    assert "run_decay_service()" not in source
    assert "run_decay_tenant_work(tenant_id, run_decay_service)" in source
    assert 'or "default"' not in source
