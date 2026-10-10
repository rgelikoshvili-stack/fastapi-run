"""Isolated tests for startup side-effect controls; no external work is run."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.startup.controls import (
    migrations_enabled,
    read_bool_env,
    startup_maintenance_enabled,
    startup_work_enabled,
)


@pytest.mark.parametrize(
    "raw,expected",
    [("true", True), ("1", True), ("false", False), ("0", False), (" TRUE ", True), ("False", False)],
)
def test_boolean_control_accepts_only_explicit_values(monkeypatch, raw, expected):
    monkeypatch.setenv("SAFE_TEST_FLAG", raw)
    assert read_bool_env("SAFE_TEST_FLAG", default=not expected) is expected


def test_missing_boolean_control_uses_documented_default(monkeypatch):
    monkeypatch.delenv("SAFE_TEST_FLAG", raising=False)
    assert read_bool_env("SAFE_TEST_FLAG", default=True) is True


def test_invalid_boolean_control_fails_closed(monkeypatch):
    monkeypatch.setenv("SAFE_TEST_FLAG", "sometimes")
    with pytest.raises(ValueError):
        read_bool_env("SAFE_TEST_FLAG", default=True)


@pytest.mark.parametrize(
    "startup,skip,expected",
    [(None, None, True), ("true", "false", True), ("true", "true", False), ("false", "false", False)],
)
def test_migration_gate_defaults_and_precedence(monkeypatch, startup, skip, expected):
    for key, value in (("BRIDGEHUB_STARTUP_WORK_ENABLED", startup), ("SKIP_MIGRATIONS", skip)):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    assert migrations_enabled() is expected


@pytest.mark.parametrize(
    "startup,maintenance,expected",
    [(None, None, True), ("true", None, True), ("true", "false", False), ("false", "invalid", False)],
)
def test_maintenance_gate_defaults_and_master_precedence(monkeypatch, startup, maintenance, expected):
    for key, value in (
        ("BRIDGEHUB_STARTUP_WORK_ENABLED", startup),
        ("BRIDGEHUB_STARTUP_MAINTENANCE_ENABLED", maintenance),
    ):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    assert startup_maintenance_enabled() is expected


def test_invalid_skip_migrations_is_not_enabled(monkeypatch):
    monkeypatch.setenv("BRIDGEHUB_STARTUP_WORK_ENABLED", "true")
    monkeypatch.setenv("SKIP_MIGRATIONS", "maybe")
    with pytest.raises(ValueError):
        migrations_enabled()


def test_direct_migration_entrypoint_is_guarded_without_db_access(monkeypatch):
    monkeypatch.setenv("BRIDGEHUB_STARTUP_WORK_ENABLED", "false")
    monkeypatch.setenv("SKIP_MIGRATIONS", "false")
    with patch("app.api.db.get_db_sync", side_effect=AssertionError("DB access attempted")):
        from app.startup.migrations import run_db_migrations

        assert run_db_migrations() is False


def test_direct_migration_entrypoint_honors_skip_flag_without_db_access(monkeypatch):
    monkeypatch.setenv("BRIDGEHUB_STARTUP_WORK_ENABLED", "true")
    monkeypatch.setenv("SKIP_MIGRATIONS", "true")
    with patch("app.api.db.get_db_sync", side_effect=AssertionError("DB access attempted")):
        from app.startup.migrations import run_db_migrations

        assert run_db_migrations() is False


@pytest.mark.parametrize(
    "key,value",
    [("BRIDGEHUB_STARTUP_WORK_ENABLED", "sometimes"), ("SKIP_MIGRATIONS", "sometimes")],
)
def test_direct_migration_entrypoint_fails_closed_on_invalid_controls(monkeypatch, key, value):
    monkeypatch.setenv("BRIDGEHUB_STARTUP_WORK_ENABLED", "true")
    monkeypatch.setenv("SKIP_MIGRATIONS", "false")
    monkeypatch.setenv(key, value)
    with patch("app.api.db.get_db_sync", side_effect=AssertionError("DB access attempted")):
        from app.startup.migrations import run_db_migrations

        assert run_db_migrations() is False


def test_management_and_standalone_migration_commands_respect_guard(monkeypatch):
    monkeypatch.setenv("BRIDGEHUB_STARTUP_WORK_ENABLED", "false")
    monkeypatch.setenv("SKIP_MIGRATIONS", "false")
    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic.invalid/nonproduction")
    with patch("app.api.db.get_db_sync", side_effect=AssertionError("DB access attempted")):
        from manage import cmd_migrate
        from scripts.migrate import live_run

        cmd_migrate([])
        live_run()


def test_background_task_factory_does_not_schedule_when_disabled(monkeypatch):
    monkeypatch.setenv("BRIDGEHUB_STARTUP_WORK_ENABLED", "false")
    import main

    with patch("asyncio.create_task", side_effect=AssertionError("task scheduled")):
        assert main._create_background_tasks() == []


def test_disabled_lifespan_skips_all_startup_tasks_and_maintenance(monkeypatch):
    monkeypatch.setenv("BRIDGEHUB_STARTUP_WORK_ENABLED", "false")
    monkeypatch.setenv("GCP_PROJECT_ID", "")
    monkeypatch.setenv("USE_SECRET_MANAGER", "false")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    import main

    async def run_lifespan():
        with patch("app.api.services.auth_service.validate_jwt_secret_at_startup"), \
             patch.object(main, "_create_background_tasks", side_effect=AssertionError("workers started")), \
             patch("asyncio.create_task", side_effect=AssertionError("maintenance scheduled")):
            async with main.lifespan(main.app):
                assert main.app.state.background_tasks == []

    asyncio.run(run_lifespan())


def test_invalid_startup_control_fails_before_any_task_is_scheduled(monkeypatch):
    monkeypatch.setenv("BRIDGEHUB_STARTUP_WORK_ENABLED", "ambiguous")
    import main

    async def run_lifespan():
        with patch("asyncio.create_task", side_effect=AssertionError("task scheduled")):
            async with main.lifespan(main.app):
                raise AssertionError("invalid control was accepted")

    with pytest.raises(ValueError):
        asyncio.run(run_lifespan())


def test_enabled_background_registration_uses_mocks_only(monkeypatch):
    monkeypatch.setenv("BRIDGEHUB_STARTUP_WORK_ENABLED", "true")
    scheduled = []

    async def harmless():
        return None

    class FakeTask:
        def add_done_callback(self, callback):
            self.callback = callback

    def fake_create_task(coro, *, name):
        scheduled.append(name)
        coro.close()
        return FakeTask()

    import main
    monkeypatch.setattr(main, "autopilot_loop", harmless)
    monkeypatch.setattr(main, "decay_loop", harmless)
    monkeypatch.setattr(main, "email_poller_loop", harmless)
    monkeypatch.setattr(main, "_nbg_sync_loop", harmless)
    with patch("asyncio.create_task", side_effect=fake_create_task):
        tasks = main._create_background_tasks()
    assert scheduled == ["autopilot_loop", "decay_loop", "email_poller_loop", "nbg_sync_loop"]
    assert len(tasks) == 4


def test_lifespan_can_register_loops_without_scheduling_startup_maintenance(monkeypatch):
    monkeypatch.setenv("BRIDGEHUB_STARTUP_WORK_ENABLED", "true")
    monkeypatch.setenv("BRIDGEHUB_STARTUP_MAINTENANCE_ENABLED", "false")
    monkeypatch.setenv("SKIP_MIGRATIONS", "true")
    import main

    scheduled = []
    class FakeTask:
        def add_done_callback(self, callback):
            self.callback = callback

    def fake_create_task(coro, *, name):
        scheduled.append(name)
        coro.close()
        return FakeTask()

    async def run_lifespan():
        with patch("app.api.services.auth_service.validate_jwt_secret_at_startup") as jwt_validate, \
             patch.object(main, "_create_background_tasks", return_value=[FakeTask()]) as make_loops, \
             patch.object(main, "_cancel_background_tasks", new_callable=AsyncMock):
            with patch("asyncio.create_task", side_effect=fake_create_task):
                async with main.lifespan(main.app):
                    assert main.app.state.background_tasks
            jwt_validate.assert_called_once()
            make_loops.assert_called_once()
        assert scheduled == []

    asyncio.run(run_lifespan())


def test_startup_maintenance_is_guarded_before_pool_or_side_effects(monkeypatch):
    monkeypatch.setenv("BRIDGEHUB_STARTUP_WORK_ENABLED", "false")
    import main

    async def run():
        with patch("app.api.db.get_pool", side_effect=AssertionError("pool started")), \
             patch.object(main, "_run_db_migrations", side_effect=AssertionError("migration ran")):
            await main._run_startup_maintenance()

    asyncio.run(run())


def test_maintenance_disabled_returns_before_pool_or_migration_side_effects(monkeypatch):
    monkeypatch.setenv("BRIDGEHUB_STARTUP_WORK_ENABLED", "true")
    monkeypatch.setenv("BRIDGEHUB_STARTUP_MAINTENANCE_ENABLED", "false")
    monkeypatch.setenv("SKIP_MIGRATIONS", "true")
    import main

    async def run():
        with patch("app.api.db.get_pool", side_effect=AssertionError("pool started")), \
             patch.object(main, "_run_db_migrations", side_effect=AssertionError("migration ran")), \
             patch.object(main, "_ensure_email_tables", side_effect=AssertionError("maintenance ran")):
            await main._run_startup_maintenance()

    asyncio.run(run())


def test_invalid_maintenance_control_fails_lifespan_before_auth_or_workers(monkeypatch):
    monkeypatch.setenv("BRIDGEHUB_STARTUP_WORK_ENABLED", "true")
    monkeypatch.setenv("BRIDGEHUB_STARTUP_MAINTENANCE_ENABLED", "sometimes")
    import main

    async def run_lifespan():
        with patch("app.api.services.auth_service.validate_jwt_secret_at_startup") as jwt_validate, \
             patch.object(main, "_create_background_tasks", side_effect=AssertionError("workers started")), \
             patch("asyncio.create_task", side_effect=AssertionError("task scheduled")):
            async with main.lifespan(main.app):
                raise AssertionError("invalid maintenance control accepted")

    with pytest.raises(ValueError):
        asyncio.run(run_lifespan())


def test_invalid_skip_value_stops_maintenance_before_pool_access(monkeypatch):
    monkeypatch.setenv("BRIDGEHUB_STARTUP_WORK_ENABLED", "true")
    monkeypatch.setenv("BRIDGEHUB_STARTUP_MAINTENANCE_ENABLED", "true")
    monkeypatch.setenv("SKIP_MIGRATIONS", "ambiguous")
    import main

    async def run():
        with patch("app.api.db.get_pool", side_effect=AssertionError("pool started")):
            with pytest.raises(ValueError):
                await main._run_startup_maintenance()

    asyncio.run(run())
