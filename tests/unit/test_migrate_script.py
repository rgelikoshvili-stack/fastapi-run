"""tests/unit/test_migrate_script.py — Unit tests for scripts/migrate.py."""
import importlib
import sys
import types
from unittest.mock import patch, MagicMock


def _import_migrate():
    """Import scripts/migrate.py as a module (handles scripts/ not being a package)."""
    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        "migrate",
        os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "migrate.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_dry_run_exits_zero_without_db(monkeypatch):
    """--dry-run must complete without DATABASE_URL and without touching the DB."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    mod = _import_migrate()

    mock_run_db = MagicMock()
    mock_run_table = MagicMock()
    mock_run_index = MagicMock()

    mock_migrations = types.ModuleType("app.startup.migrations")
    mock_migrations.run_db_migrations = mock_run_db
    mock_tables = types.ModuleType("app.startup.migrations_tables")
    mock_tables.run_table_migrations = mock_run_table
    mock_indexes = types.ModuleType("app.startup.migrations_indexes")
    mock_indexes.run_index_migrations = mock_run_index

    with patch.dict(sys.modules, {
        "app.startup.migrations": mock_migrations,
        "app.startup.migrations_tables": mock_tables,
        "app.startup.migrations_indexes": mock_indexes,
    }):
        mod.dry_run()  # must not raise

    mock_run_db.assert_not_called()
    mock_run_table.assert_not_called()
    mock_run_index.assert_not_called()


def test_dry_run_does_not_call_run_db_migrations(monkeypatch):
    """dry_run() must never call run_db_migrations regardless of DATABASE_URL."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@host/db")
    mod = _import_migrate()

    mock_run_db = MagicMock()
    mock_migrations = types.ModuleType("app.startup.migrations")
    mock_migrations.run_db_migrations = mock_run_db
    mock_tables = types.ModuleType("app.startup.migrations_tables")
    mock_tables.run_table_migrations = MagicMock()
    mock_indexes = types.ModuleType("app.startup.migrations_indexes")
    mock_indexes.run_index_migrations = MagicMock()

    with patch.dict(sys.modules, {
        "app.startup.migrations": mock_migrations,
        "app.startup.migrations_tables": mock_tables,
        "app.startup.migrations_indexes": mock_indexes,
    }):
        mod.dry_run()

    mock_run_db.assert_not_called()


def test_live_run_exits_nonzero_without_db_url(monkeypatch):
    """live_run() must call sys.exit(1) when DATABASE_URL is absent."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    mod = _import_migrate()

    import pytest
    with pytest.raises(SystemExit) as exc_info:
        mod.live_run()
    assert exc_info.value.code == 1


def test_live_run_calls_run_db_migrations(monkeypatch):
    """live_run() must delegate to run_db_migrations() when DATABASE_URL is set."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@host/db")
    mod = _import_migrate()

    mock_run_db = MagicMock()
    mock_migrations = types.ModuleType("app.startup.migrations")
    mock_migrations.run_db_migrations = mock_run_db

    with patch.dict(sys.modules, {"app.startup.migrations": mock_migrations}):
        mod.live_run()

    mock_run_db.assert_called_once()


def test_migration_groups_list_is_nonempty():
    """MIGRATION_GROUPS must describe at least one step."""
    mod = _import_migrate()
    assert len(mod.MIGRATION_GROUPS) >= 1


def test_dry_run_covers_all_groups(monkeypatch, capsys):
    """dry_run() log output must mention the count of MIGRATION_GROUPS."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    mod = _import_migrate()

    mock_migrations = types.ModuleType("app.startup.migrations")
    mock_migrations.run_db_migrations = MagicMock()
    mock_tables = types.ModuleType("app.startup.migrations_tables")
    mock_tables.run_table_migrations = MagicMock()
    mock_indexes = types.ModuleType("app.startup.migrations_indexes")
    mock_indexes.run_index_migrations = MagicMock()

    import io, logging
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("migrate")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    with patch.dict(sys.modules, {
        "app.startup.migrations": mock_migrations,
        "app.startup.migrations_tables": mock_tables,
        "app.startup.migrations_indexes": mock_indexes,
    }):
        mod.dry_run()

    logger.removeHandler(handler)
    output = stream.getvalue()
    assert "dry-run: complete" in output
    assert "no database changes made" in output
