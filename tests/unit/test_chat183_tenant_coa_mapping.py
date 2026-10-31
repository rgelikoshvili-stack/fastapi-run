"""Chat183: tenant-specific COA mapping is explicit, reviewed and fail closed."""
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.api.db import authenticated_tenant_context
from app.api.services.posted_ledger_reporting import UnclassifiedLedgerAccount


def reviewed(code="X-900", tenant="t_alpha", kind="expense", **overrides):
    row = {
        "tenant_id": tenant, "account_code": code, "account_type": kind,
        "effective_from": date(2026, 10, 1), "effective_until": None,
        "source_system": "reviewed-erp", "source_revision": "rev-a",
        "source_sha256": "a" * 64, "approved_by": "different-reviewer",
        "approved_at": datetime(2026, 10, 29, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return row


def lines(code="X-900"):
    return [{"account_code": "1120", "debit": "10", "account_type": "income"},
            {"account_code": code, "credit": "10", "account_type": "asset"}]


@pytest.mark.asyncio
async def test_disabled_mapping_refuses_unknown_without_io(monkeypatch):
    from app.api.services.tenant_coa_mapping_service import classify_tenant_ledger_lines
    monkeypatch.delenv("TENANT_COA_MAPPINGS_ENABLED", raising=False)
    conn = AsyncMock()
    with pytest.raises(UnclassifiedLedgerAccount, match="LEDGER_ACCOUNT_UNCLASSIFIED"):
        await classify_tenant_ledger_lines(lines(), "t_alpha", "2026-10-30", conn=conn)
    conn.fetch.assert_not_called()


@pytest.mark.asyncio
async def test_canonical_mapping_never_uses_client_type_or_db(monkeypatch):
    from app.api.services.tenant_coa_mapping_service import classify_tenant_ledger_lines
    monkeypatch.setenv("TENANT_COA_MAPPINGS_ENABLED", "true")
    conn = AsyncMock()
    typed = await classify_tenant_ledger_lines(lines("6110"), "t_alpha", "2026-10-30", conn=conn)
    assert [line["account_type"] for line in typed] == ["asset", "income"]
    conn.fetch.assert_not_called()


@pytest.mark.asyncio
async def test_approved_mapping_only_with_authorized_tenant_context(monkeypatch):
    from app.api.services.tenant_coa_mapping_service import classify_tenant_ledger_lines
    monkeypatch.setenv("TENANT_COA_MAPPINGS_ENABLED", "true")
    conn = AsyncMock()
    conn.fetch.return_value = [reviewed()]
    with pytest.raises(UnclassifiedLedgerAccount):
        await classify_tenant_ledger_lines(lines(), "t_alpha", "2026-10-30", conn=conn)
    conn.fetch.assert_not_called()
    with authenticated_tenant_context("t_alpha"):
        typed = await classify_tenant_ledger_lines(lines(), "t_alpha", "2026-10-30", conn=conn)
    assert [x["account_type"] for x in typed] == ["asset", "expense"]
    args = conn.fetch.call_args.args
    assert args[1] == "t_alpha" and args[2] == ["X-900"] and args[3] == date(2026, 10, 30)


@pytest.mark.asyncio
@pytest.mark.parametrize("rows", [
    [], [reviewed(tenant="t_beta")], [reviewed(kind="revenue")],
    [reviewed(approved_by="")], [reviewed(source_sha256="bad")],
    [reviewed(), reviewed(effective_from=date(2026, 10, 15))],
    [reviewed(effective_until=date(2026, 10, 18))],
    [reviewed(account_code="6110")],
])
async def test_incomplete_foreign_overlap_or_unreviewed_rows_refused(monkeypatch, rows):
    from app.api.services.tenant_coa_mapping_service import classify_tenant_ledger_lines
    monkeypatch.setenv("TENANT_COA_MAPPINGS_ENABLED", "true")
    conn = AsyncMock()
    conn.fetch.return_value = rows
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(UnclassifiedLedgerAccount, match="LEDGER_ACCOUNT_UNCLASSIFIED"):
            await classify_tenant_ledger_lines(lines(), "t_alpha", "2026-10-30", conn=conn)


@pytest.mark.asyncio
async def test_mismatched_tenant_and_missing_db_fail_closed(monkeypatch):
    from app.api.services.tenant_coa_mapping_service import classify_tenant_ledger_lines
    monkeypatch.setenv("TENANT_COA_MAPPINGS_ENABLED", "true")
    conn = AsyncMock()
    conn.fetch.side_effect = RuntimeError("private SQL / credentials")
    with authenticated_tenant_context("t_alpha"):
        with pytest.raises(UnclassifiedLedgerAccount):
            await classify_tenant_ledger_lines(lines(), "t_beta", "2026-10-30", conn=conn)
        conn.fetch.assert_not_called()
        with pytest.raises(UnclassifiedLedgerAccount) as exc:
            await classify_tenant_ledger_lines(lines(), "t_alpha", "2026-10-30", conn=conn)
    assert "private" not in str(exc.value)


@pytest.mark.asyncio
async def test_writer_persists_reviewed_type_and_refuses_unapproved_before_insert(monkeypatch):
    from app.api.services.posting_service import _write_ledger_entries
    monkeypatch.setenv("TENANT_COA_MAPPINGS_ENABLED", "true")
    conn = AsyncMock()
    conn.is_in_transaction = lambda: True
    conn.fetchval.side_effect = [None, "synthetic-header"]
    conn.fetch.return_value = [reviewed()]
    draft = {"id": "chat183-test", "tenant_id": "t_alpha",
             "date": "2026-10-30", "currency": "GEL", "lines": lines()}
    with authenticated_tenant_context("t_alpha"):
        await _write_ledger_entries(conn, draft, {}, "t_alpha", "mock", "synthetic")
    inserts = [c for c in conn.execute.call_args_list
               if "INSERT INTO journal_entry_lines" in c.args[0]]
    assert len(inserts) == 2
    assert [c.args[-1] for c in inserts] == ["asset", "expense"]
    assert not any("private" in str(c) for c in inserts)


@pytest.mark.asyncio
async def test_payload_preflight_uses_reviewed_mapping_before_connector(monkeypatch):
    from app.api.services import tenant_coa_mapping_service as svc, posting_service
    monkeypatch.setenv("TENANT_COA_MAPPINGS_ENABLED", "true")
    monkeypatch.setenv("POSTED_LEDGER_WRITES_ENABLED", "true")
    conn = AsyncMock()
    conn.fetch.return_value = [reviewed()]
    @asynccontextmanager
    async def scoped():
        yield conn
    monkeypatch.setattr(svc, "get_conn", scoped)
    draft = {"id": "chat183", "tenant_id": "t_alpha", "date": "2026-10-30",
             "currency": "GEL", "amount": 10, "lines": lines()}
    with authenticated_tenant_context("t_alpha"):
        payload = await posting_service._draft_to_posting_payload(draft)
    assert payload["lines"][1]["account_type"] == "expense"
