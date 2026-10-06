from contextlib import asynccontextmanager

import pytest

from app.api import db
from app.api.services import admin_dashboard_service, export_service, saas_service, system_service


@pytest.mark.asyncio
async def test_admin_summary_reads_each_tenant_usage_inside_its_context(monkeypatch):
    tenants = [
        {"tenant_id": "tenant-a", "name": "A", "plan": "FREE", "is_active": True,
         "status": "active", "created_at": "2026-01-01"},
        {"tenant_id": "tenant-b", "name": "B", "plan": "FREE", "is_active": True,
         "status": "active", "created_at": "2026-01-02"},
    ]
    scoped_queries = []

    class Conn:
        async def fetch(self, query):
            if "GROUP BY plan" in query:
                return [{"plan": "FREE", "cnt": 2}]
            return tenants

        async def fetchval(self, query, tenant_id):
            assert "WHERE tenant_id" in query
            assert db.require_current_tenant_id(tenant_id) == tenant_id
            scoped_queries.append(tenant_id)
            return 4 if tenant_id == "tenant-a" else 7

    @asynccontextmanager
    async def fake_get_conn():
        yield Conn()

    async def fake_get_usage(tenant_id, _month):
        assert db.require_current_tenant_id(tenant_id) == tenant_id
        return {"draft_count": 1, "user_count": 2}

    monkeypatch.setattr(admin_dashboard_service, "get_conn", fake_get_conn)
    monkeypatch.setattr(admin_dashboard_service, "get_usage", fake_get_usage)

    with db.authenticated_tenant_context("admin-home-tenant"):
        result = await admin_dashboard_service.get_tenant_summary()

    assert result["total_drafts"] == 11
    assert result["total_tenants"] == 2
    assert scoped_queries == ["tenant-a", "tenant-b"]
    assert db._current_tenant_id.get() is None


@pytest.mark.asyncio
async def test_admin_detail_resolves_target_from_control_plane_then_scopes_reads(monkeypatch):
    observed_contexts = []

    class Conn:
        async def fetchrow(self, query, tenant_id):
            if "FROM tenants" in query:
                assert db._current_tenant_id.get() is None
                return {"tenant_id": "tenant-b", "plan": "FREE", "name": "B"}
            assert "FROM journal_drafts" in query
            assert db.require_current_tenant_id(tenant_id) == "tenant-b"
            observed_contexts.append(tenant_id)
            return {"total": 0, "posted": 0, "drafted": 0, "rejected": 0, "posted_amount": 0}

        async def fetchval(self, query, tenant_id):
            assert db.require_current_tenant_id(tenant_id) == "tenant-b"
            observed_contexts.append(tenant_id)
            return 0

    @asynccontextmanager
    async def fake_get_conn():
        yield Conn()

    async def fake_get_usage(tenant_id, _month):
        assert db.require_current_tenant_id(tenant_id) == "tenant-b"
        observed_contexts.append(tenant_id)
        return {"draft_count": 0, "user_count": 0}

    monkeypatch.setattr(admin_dashboard_service, "get_conn", fake_get_conn)
    monkeypatch.setattr(admin_dashboard_service, "get_usage", fake_get_usage)

    with db.authenticated_tenant_context("admin-home-tenant"):
        result = await admin_dashboard_service.get_tenant_detail("tenant-b")

    assert result["tenant"]["tenant_id"] == "tenant-b"
    assert observed_contexts == ["tenant-b", "tenant-b", "tenant-b"]
    assert db._current_tenant_id.get() is None


@pytest.mark.asyncio
async def test_tenant_owned_service_queries_reject_missing_context_before_db(monkeypatch):
    async def unexpected_db():
        raise AssertionError("database must not be touched without tenant context")

    monkeypatch.setattr(export_service, "get_conn", unexpected_db)
    monkeypatch.setattr(saas_service, "get_conn", unexpected_db)
    monkeypatch.setattr(system_service, "get_conn", unexpected_db)

    with pytest.raises(ValueError, match="tenant DB context is required"):
        await export_service.get_journal_drafts("tenant-a")
    with pytest.raises(ValueError, match="tenant DB context is required"):
        await saas_service.get_usage("tenant-a")
    with pytest.raises(ValueError, match="tenant DB context is required"):
        await system_service.get_system_summary_service("tenant-a")


@pytest.mark.asyncio
async def test_tenant_owned_service_rejects_mismatched_tenant_hint_before_db(monkeypatch):
    async def unexpected_db():
        raise AssertionError("database must not be touched for a mismatched tenant")

    monkeypatch.setattr(export_service, "get_conn", unexpected_db)
    monkeypatch.setattr(saas_service, "get_conn", unexpected_db)
    with db.authenticated_tenant_context("tenant-a"):
        with pytest.raises(ValueError, match="does not match"):
            await export_service.get_journal_drafts("tenant-b")
        with pytest.raises(ValueError, match="does not match"):
            await saas_service.get_usage("tenant-b")
