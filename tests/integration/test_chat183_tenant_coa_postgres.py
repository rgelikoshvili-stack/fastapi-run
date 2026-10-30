"""Chat183: actual disposable PG15/16 tenant COA row-level isolation.

Never connects outside Chat162 synthetic localhost. No production DDL.
"""
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
import pytest

from app.api.db import authenticated_tenant_context
from app.api.services.tenant_coa_mapping_service import classify_tenant_ledger_lines
from app.api.services.posted_ledger_reporting import UnclassifiedLedgerAccount


def dsn():
    import os
    u = urlsplit(os.getenv("CHAT162_TEST_DATABASE_URL", ""))
    if not u.scheme:
        pytest.skip("Disposable PG15/16 absent")
    if not (u.scheme in {"postgres", "postgresql"} and u.hostname == "127.0.0.1"
            and u.port == 55442 and u.path == "/bridge_hub_chat162_test"
            and u.username == "chat162_test_user"):
        raise RuntimeError("Refusing COA tests against non-disposable PostgreSQL")
    return u.geturl()


@pytest.mark.asyncio
async def test_coa_approved_tenant_scope_force_rls_and_no_mutation(monkeypatch):
    monkeypatch.setenv("TENANT_COA_MAPPINGS_ENABLED", "true")
    url = dsn()
    suffix = uuid4().hex
    schema, role = "chat183_" + suffix, "chat183_role_" + suffix
    admin = await asyncpg.connect(url)
    runtime = None
    created_role = False
    created_schema = False
    try:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        created_schema = True
        await admin.execute(f'CREATE ROLE "{role}" LOGIN PASSWORD \'chat183-only-test\' NOBYPASSRLS')
        created_role = True
        await admin.execute(f'SET search_path TO "{schema}"')
        sql = Path("docs/sql/chat183_tenant_coa_mappings_DRAFT.sql").read_text(encoding="utf-8")
        await admin.execute(sql)
        await admin.execute(sql)  # idempotent DDL and policy
        await admin.executemany("""
            INSERT INTO tenant_coa_mappings (
              tenant_id, account_code, account_type, effective_from,
              source_system, source_revision, source_sha256, approved_by, approved_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW())
        """, [
            ("t_alpha", "X-900", "expense", date(2026,10,1),
             "reviewed-erp", "rev-a", "a"*64, "reviewer"),
            ("t_beta", "X-900", "liability", date(2026,10,1),
             "reviewed-erp", "rev-b", "b"*64, "reviewer"),
        ])
        await admin.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"')
        await admin.execute(f'GRANT SELECT ON tenant_coa_mappings TO "{role}"')
        url_obj = urlsplit(url)
        runtime_url = (f"postgresql://{role}:chat183-only-test@127.0.0.1:"
                       f"{url_obj.port}{url_obj.path}")
        runtime = await asyncpg.connect(runtime_url, server_settings={"search_path": schema})
        assert await runtime.fetchval("SELECT COUNT(*) FROM tenant_coa_mappings") == 0
        for tenant, expected in (("t_alpha", "expense"), ("t_beta", "liability")):
            async with runtime.transaction():
                await runtime.execute("SELECT set_config('app.current_tenant_id', $1, true)", tenant)
                rows = await runtime.fetch("SELECT * FROM tenant_coa_mappings")
                assert len(rows) == 1 and rows[0]["tenant_id"] == tenant
                with authenticated_tenant_context(tenant):
                    result = await classify_tenant_ledger_lines(
                        [{"account_code": "X-900", "debit": "1"}],
                        tenant, "2026-10-30", conn=runtime)
                    assert result[0]["account_type"] == expected
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await runtime.execute("DELETE FROM tenant_coa_mappings")
        with authenticated_tenant_context("t_alpha"):
            with pytest.raises(UnclassifiedLedgerAccount):
                await classify_tenant_ledger_lines(
                    [{"account_code": "X-900", "credit": "1"}],
                    "t_alpha", "2026-10-30", conn=runtime)
    finally:
        if runtime is not None:
            await runtime.close()
        if created_schema:
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        if created_role:
            await admin.execute(f'DROP ROLE "{role}"')
        await admin.close()
