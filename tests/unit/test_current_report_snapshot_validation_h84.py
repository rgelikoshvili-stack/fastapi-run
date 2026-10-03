from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import validate_h84_report_snapshots as h84


DOC = Path("docs/current_report_snapshot_validation_h84.md")


def test_dsn_accepts_only_exact_disposable_local_target():
    h84.validate_test_dsn(
        "postgresql://tester:placeholder@127.0.0.1:55434/bridge_hub_h84_test"
    )


@pytest.mark.parametrize("dsn", [
    "postgresql://tester:placeholder@localhost:55434/bridge_hub_h84_test",
    "postgresql://tester:placeholder@127.0.0.1:5432/bridge_hub_h84_test",
    "postgresql://tester:placeholder@127.0.0.1:55434/production",
    "postgresql://tester:placeholder@db.example.com:55434/bridge_hub_h84_test",
])
def test_dsn_rejects_nonapproved_targets(dsn):
    with pytest.raises(ValueError):
        h84.validate_test_dsn(dsn)


def test_helper_uses_dedicated_dsn_name_and_never_reads_production_url():
    source = Path("scripts/validate_h84_report_snapshots.py").read_text(encoding="utf-8")
    assert 'H84_REPORT_TEST_DATABASE_URL' in source
    assert 'os.environ.get("DATABASE_URL"' not in source
    assert "get_secret" not in source
    assert "REPOSITORY_ROOT" in source and "sys.path.insert" in source
    assert "127.0.0.1" in source and "55434" in source and "bridge_hub_h84_test" in source
    assert "print(dsn" not in source.lower()


def test_helper_uses_and_cleans_a_temporary_synthetic_schema():
    source = Path("scripts/validate_h84_report_snapshots.py").read_text(encoding="utf-8")
    assert "CREATE SCHEMA" in source
    assert "DROP SCHEMA IF EXISTS" in source
    assert "uuid4().hex" in source
    assert "other tenant only" in source
    assert "must not be official" in source


def test_disposable_postgres_workflow_is_test_only_and_runs_helper():
    workflow = Path(".github/workflows/pr84-postgres-snapshot.yml").read_text(encoding="utf-8")
    assert "image: postgres:16" in workflow
    assert "POSTGRES_DB: bridge_hub_h84_test" in workflow
    assert "POSTGRES_PASSWORD: h84_test_only_password" in workflow
    assert "DATABASE_URL: \"\"" in workflow
    assert "H84_REPORT_TEST_DATABASE_URL:" in workflow
    assert "python scripts/validate_h84_report_snapshots.py" in workflow
    assert "secrets." not in workflow
    assert "deploy.yml" not in workflow


def test_snapshot_builders_use_tenant_scoped_posted_ledger_queries():
    from app.api.services import financial_statements_service as reports

    builder_calls = (
        (reports._build_posted_trial_balance_as_of_query, (h84.TENANT_ALPHA, "2026-09-30")),
        (reports._build_pnl_posted_ledger_query, (h84.TENANT_ALPHA, "2026-09-01", "2026-09-30")),
        (reports._build_balance_sheet_posted_ledger_query, (h84.TENANT_ALPHA, "2026-09-30")),
        (reports._build_cashflow_posted_ledger_query, (h84.TENANT_ALPHA, "2026-09-01", "2026-09-30")),
    )
    for builder, args in builder_calls:
        sql, params = builder(*args)
        normalized = " ".join(sql.lower().split())
        assert "journal_entry_headers" in normalized
        assert "journal_entry_lines" in normalized
        assert "tenant_id = $1" in normalized
        assert "status = any($2)" in normalized
        assert "journal_drafts" not in normalized
        assert params[0] == h84.TENANT_ALPHA
        assert set(params[1]) == {"posted", "correction"}


def test_document_labels_snapshots_and_expired_h53_approval():
    text = DOC.read_text(encoding="utf-8")
    for snapshot in ("Trial balance", "P&L", "Balance Sheet", "Cashflow"):
        assert snapshot in text
    assert "expired on May 25, 2026" in text
    assert "H84_REPORT_TEST_DATABASE_URL" in text
    assert "journal_drafts" in text


@pytest.mark.asyncio
async def test_report_capture_calls_current_posted_report_builders(monkeypatch):
    from app.api import db
    from app.api.services import financial_statements_service as reports

    calls = []
    async def trial_balance(tenant, as_of):
        calls.append(("trial_balance", tenant, as_of))
        return {"1120": 38.0, "1510": 30.0}

    async def pnl(tenant, date_from, date_to):
        calls.append(("pnl", tenant, date_from, date_to))
        return {"ok": True, "data": {
            "source": "posted_ledger", "revenue": {"total": 100.0},
            "opex": {"total": 100.0},
        }}

    async def balance_sheet(tenant, as_of):
        calls.append(("balance_sheet", tenant, as_of))
        return {"ok": True, "data": {
            "source": "posted_ledger", "as_of": as_of,
            "assets": {"total": 68.0}, "balanced": True,
        }}

    async def cashflow(tenant, date_from, date_to):
        calls.append(("cashflow", tenant, date_from, date_to))
        return {"ok": True, "data": {
            "operating": {"inflows": 118.0, "outflows": 100.0},
            "investing": {"outflows": 30.0},
            "financing": {"inflows": 50.0},
        }}

    monkeypatch.setattr(reports, "_get_posted_trial_balance_as_of", trial_balance)
    monkeypatch.setattr(reports, "build_profit_and_loss", pnl)
    monkeypatch.setattr(reports, "build_balance_sheet", balance_sheet)
    monkeypatch.setattr(reports, "build_cashflow_statement", cashflow)
    monkeypatch.setattr(db, "_async_pool", object())
    monkeypatch.setenv("POSTED_LEDGER_REPORTS_ENABLED", "0")

    result = await h84.capture_current_reports(object())

    assert result["official_sources"]["journal_drafts_used_for_official_values"] is False
    assert result["official_sources"]["profit_and_loss"] == "posted_ledger"
    assert {call[0] for call in calls} == {"trial_balance", "pnl", "balance_sheet", "cashflow"}
    assert all(call[1] == h84.TENANT_ALPHA for call in calls)
    assert os.environ["POSTED_LEDGER_REPORTS_ENABLED"] == "0"
