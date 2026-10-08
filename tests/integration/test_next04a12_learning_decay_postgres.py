"""Disposable PostgreSQL 16 proof for scheduled learning-decay tenant scoping."""
import os
import uuid
from urllib.parse import urlparse

import psycopg2
import pytest
from psycopg2 import sql

from app.api import db
from app.api.db import require_current_tenant_id
from app.api.services.learning_service import run_decay_service
from app.startup.background import run_decay_tenant_work


def _disposable_url() -> str:
    value = os.getenv("NEXT04A_TEST_DATABASE_URL", "")
    if not value:
        pytest.skip("NEXT04A_TEST_DATABASE_URL is required")
    parsed = urlparse(value)
    assert parsed.scheme in {"postgres", "postgresql"}
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1", "postgres"}
    return value


def _close_sync_pool() -> None:
    if db._sync_pool is not None:
        db._sync_pool.closeall()
        db._sync_pool = None


@pytest.mark.asyncio
async def test_decay_isolated_by_tenant_and_repeated_runs(monkeypatch):
    admin_url = _disposable_url()
    schema = f"next04a12_{uuid.uuid4().hex[:10]}"
    with psycopg2.connect(admin_url) as admin:
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            cur.execute(sql.SQL("""CREATE TABLE {}.learning_patterns (
                id bigint PRIMARY KEY,
                tenant_id text NOT NULL,
                status text NOT NULL,
                updated_at timestamptz NOT NULL
            )""").format(sql.Identifier(schema)))
            cur.execute(sql.SQL("""INSERT INTO {}.learning_patterns
                (id, tenant_id, status, updated_at) VALUES
                (1, 'tenant-a', 'active', NOW() - INTERVAL '60 days'),
                (2, 'tenant-b', 'candidate', NOW() - INTERVAL '60 days'),
                (3, 'default',  'active', NOW() - INTERVAL '60 days'),
                (4, 'tenant-a', 'active', NOW())""").format(sql.Identifier(schema)))

    scoped_url = admin_url + ("&" if "?" in admin_url else "?") + f"options=-csearch_path%3D{schema}"
    monkeypatch.setattr("app.config.secrets.get_secret", lambda name, default=None: scoped_url if name == "DATABASE_URL" else default)
    monkeypatch.setenv("DATABASE_URL", scoped_url)
    _close_sync_pool()
    try:
        result_a = await run_decay_tenant_work("tenant-a", run_decay_service)
        assert result_a["decayed"]["decayed"] == 1
        with psycopg2.connect(admin_url) as check:
            with check.cursor() as cur:
                cur.execute(sql.SQL("SELECT tenant_id, status FROM {}.learning_patterns ORDER BY id").format(sql.Identifier(schema)))
                assert cur.fetchall() == [
                    ("tenant-a", "inactive"),
                    ("tenant-b", "candidate"),
                    ("default", "active"),
                    ("tenant-a", "active"),
                ]

        result_b = await run_decay_tenant_work("tenant-b", run_decay_service)
        assert result_b["decayed"]["decayed"] == 1
        repeated_a = await run_decay_tenant_work("tenant-a", run_decay_service)
        assert repeated_a["decayed"]["decayed"] == 0

        for invalid in (None, "", " ", "default", " DEFAULT "):
            with pytest.raises((TypeError, ValueError)):
                await run_decay_tenant_work(invalid, run_decay_service)

        with psycopg2.connect(admin_url) as check:
            with check.cursor() as cur:
                cur.execute(sql.SQL("SELECT tenant_id, status FROM {}.learning_patterns ORDER BY id").format(sql.Identifier(schema)))
                assert cur.fetchall() == [
                    ("tenant-a", "inactive"),
                    ("tenant-b", "inactive"),
                    ("default", "active"),
                    ("tenant-a", "active"),
                ]
        with pytest.raises(ValueError, match="context is required"):
            require_current_tenant_id()
    finally:
        _close_sync_pool()
        with psycopg2.connect(admin_url) as admin:
            admin.autocommit = True
            with admin.cursor() as cur:
                cur.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
