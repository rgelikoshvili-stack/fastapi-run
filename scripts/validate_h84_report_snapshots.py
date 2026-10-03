"""Capture synthetic snapshots through the current posted-ledger report services.

This opt-in helper accepts only H84_REPORT_TEST_DATABASE_URL and an explicitly
disposable local PostgreSQL target. It never reads DATABASE_URL or the secret
manager. All rows are synthetic and isolated in a temporary schema.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

REPOSITORY_ROOT = str(Path(__file__).resolve().parents[1])
if REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, REPOSITORY_ROOT)


EXPECTED_DATABASE = "bridge_hub_h84_test"
EXPECTED_HOST = "127.0.0.1"
EXPECTED_PORT = 55434
TENANT_ALPHA = "h84-tenant-alpha"
TENANT_BETA = "h84-tenant-beta"


def validate_test_dsn(dsn: str) -> None:
    """Fail closed unless the explicit DSN names this local disposable DB."""
    parsed = urlparse(dsn)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname != EXPECTED_HOST
        or parsed.port != EXPECTED_PORT
        or parsed.path.lstrip("/") != EXPECTED_DATABASE
    ):
        raise ValueError(
            "Refusing database target; H84 requires 127.0.0.1:55434/"
            "bridge_hub_h84_test via H84_REPORT_TEST_DATABASE_URL."
        )


def _schema_sql() -> str:
    return """
        CREATE TABLE journal_entry_headers (
            id UUID PRIMARY KEY, tenant_id TEXT NOT NULL, status TEXT NOT NULL,
            entry_date DATE NOT NULL, source_draft_id UUID,
            posting_log_id UUID, evidence_bundle_id UUID
        );
        CREATE TABLE journal_entry_lines (
            id UUID PRIMARY KEY, journal_entry_id UUID NOT NULL,
            tenant_id TEXT NOT NULL, account_code TEXT NOT NULL,
            account_type TEXT, cashflow_category TEXT,
            debit NUMERIC(18,2) NOT NULL DEFAULT 0,
            credit NUMERIC(18,2) NOT NULL DEFAULT 0, description TEXT
        );
        CREATE TABLE journal_drafts (
            id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL,
            status TEXT NOT NULL, journal_entries JSONB NOT NULL
        );
    """


async def _seed(conn) -> None:
    """Insert a tiny deterministic fixture with posted, draft, and other-tenant rows."""
    entries = [
        (TENANT_ALPHA, "posted", "2026-09-05", [
            ("1120", "asset", "operating", 118, 0, "synthetic customer receipt"),
            ("6110", "income", None, 0, 100, "synthetic sale"),
            ("3310", "liability", None, 0, 18, "synthetic output VAT"),
        ]),
        (TENANT_ALPHA, "posted", "2026-09-08", [
            ("7210", "expense", None, 100, 0, "synthetic operating expense"),
            ("1120", "asset", "operating", 0, 100, "synthetic bank payment"),
        ]),
        (TENANT_ALPHA, "posted", "2026-09-09", [
            ("1510", "asset", None, 30, 0, "synthetic equipment"),
            ("1120", "asset", "investing", 0, 30, "synthetic asset payment"),
        ]),
        (TENANT_ALPHA, "posted", "2026-09-10", [
            ("1120", "asset", "financing", 50, 0, "synthetic loan receipt"),
            ("3410", "liability", None, 0, 50, "synthetic loan payable"),
        ]),
        # Draft status is deliberately present in the posted-ledger tables;
        # report services must exclude it via their status filter.
        (TENANT_ALPHA, "draft", "2026-09-11", [
            ("1120", "asset", "operating", 999999, 0, "must not be official"),
            ("6110", "income", None, 0, 999999, "must not be official"),
        ]),
        (TENANT_BETA, "posted", "2026-09-06", [
            ("1120", "asset", "financing", 9000, 0, "other tenant only"),
            ("3410", "liability", None, 0, 9000, "other tenant only"),
        ]),
    ]
    from datetime import date
    from uuid import uuid4

    for tenant_id, status, entry_date, lines in entries:
        header_id = uuid4()
        await conn.execute(
            """INSERT INTO journal_entry_headers
               (id, tenant_id, status, entry_date) VALUES ($1,$2,$3,$4)""",
            header_id, tenant_id, status, date.fromisoformat(entry_date),
        )
        for code, account_type, category, debit, credit, description in lines:
            await conn.execute(
                """INSERT INTO journal_entry_lines
                   (id, journal_entry_id, tenant_id, account_code, account_type,
                    cashflow_category, debit, credit, description)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
                uuid4(), header_id, tenant_id, code, account_type, category,
                debit, credit, description,
            )
    await conn.execute(
        """INSERT INTO journal_drafts (tenant_id, status, journal_entries)
           VALUES ($1, 'draft', $2::jsonb)""",
        TENANT_ALPHA, '[{"dr":"1120","amount":"888888"}]',
    )


async def capture_current_reports(pool) -> dict:
    """Call the same posted-ledger builders used by the application."""
    from app.api import db
    from app.api.services import financial_statements_service as reports

    previous_enabled = os.environ.get("POSTED_LEDGER_REPORTS_ENABLED")
    os.environ["POSTED_LEDGER_REPORTS_ENABLED"] = "1"  # local process only
    previous_pool = db._async_pool
    db._async_pool = pool
    try:
        trial_balance = await reports._get_posted_trial_balance_as_of(
            TENANT_ALPHA, "2026-09-30"
        )
        pnl = await reports.build_profit_and_loss(
            TENANT_ALPHA, "2026-09-01", "2026-09-30"
        )
        balance_sheet = await reports.build_balance_sheet(
            TENANT_ALPHA, "2026-09-30"
        )
        cashflow = await reports.build_cashflow_statement(
            TENANT_ALPHA, "2026-09-01", "2026-09-30"
        )
        for name, report in (
            ("pnl", pnl), ("balance_sheet", balance_sheet), ("cashflow", cashflow)
        ):
            if not report.get("ok"):
                raise RuntimeError(f"{name} report unavailable: {report.get('error', {}).get('code')}")
        if pnl["data"].get("source") != "posted_ledger":
            raise RuntimeError("P&L did not identify posted-ledger source")
        if balance_sheet["data"].get("source") != "posted_ledger":
            raise RuntimeError("Balance Sheet did not identify posted-ledger source")
        if trial_balance.get("1120") != 38.0 or trial_balance.get("1510") != 30.0:
            raise RuntimeError("Trial Balance does not match the synthetic tenant-scoped expected totals")
        if pnl["data"].get("revenue", {}).get("total") != 100.0:
            raise RuntimeError("P&L revenue does not match the synthetic posted-ledger fixture")
        if pnl["data"].get("opex", {}).get("total") != 100.0:
            raise RuntimeError("P&L expense does not match the synthetic posted-ledger fixture")
        if balance_sheet["data"].get("assets", {}).get("total") != 68.0:
            raise RuntimeError("Balance Sheet assets do not match the synthetic posted-ledger fixture")
        if not balance_sheet["data"].get("balanced"):
            raise RuntimeError("Synthetic posted-ledger Balance Sheet is not balanced")
        cf = cashflow["data"]
        if (
            cf.get("operating", {}).get("inflows") != 118.0
            or cf.get("operating", {}).get("outflows") != 100.0
            or cf.get("investing", {}).get("outflows") != 30.0
            or cf.get("financing", {}).get("inflows") != 50.0
        ):
            raise RuntimeError("Cashflow categories do not match the synthetic posted-ledger fixture")
        if "journal_drafts" in json.dumps({"pnl": pnl, "bs": balance_sheet, "cf": cashflow}).lower():
            raise RuntimeError("An official report response exposed draft-source metadata")
        return {
            "scope": "synthetic_local_disposable_postgres",
            "tenant_id": TENANT_ALPHA,
            "period": {"from": "2026-09-01", "to": "2026-09-30"},
            "trial_balance": trial_balance,
            "profit_and_loss": pnl["data"],
            "balance_sheet": balance_sheet["data"],
            "cashflow": cashflow["data"],
            "official_sources": {
                "trial_balance": "posted_ledger",
                "profit_and_loss": pnl["data"]["source"],
                "balance_sheet": balance_sheet["data"]["source"],
                "cashflow": "posted_ledger_query",
                "journal_drafts_used_for_official_values": False,
            },
        }
    finally:
        db._async_pool = previous_pool
        if previous_enabled is None:
            os.environ.pop("POSTED_LEDGER_REPORTS_ENABLED", None)
        else:
            os.environ["POSTED_LEDGER_REPORTS_ENABLED"] = previous_enabled


async def run(dsn: str) -> dict:
    validate_test_dsn(dsn)
    import asyncpg

    schema = f"h84_snapshot_{uuid4().hex}"
    admin = await asyncpg.connect(dsn)
    pool = None
    try:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        pool = await asyncpg.create_pool(
            dsn, min_size=1, max_size=2,
            server_settings={"search_path": schema},
        )
        async with pool.acquire() as conn:
            await conn.execute(_schema_sql())
            await _seed(conn)
        result = await capture_current_reports(pool)
        return result
    finally:
        if pool is not None:
            await pool.close()
        await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.close()


def main() -> int:
    dsn = os.environ.get("H84_REPORT_TEST_DATABASE_URL", "")
    if not dsn:
        print("Set H84_REPORT_TEST_DATABASE_URL to the documented disposable local DB.", file=sys.stderr)
        return 2
    try:
        result = asyncio.run(run(dsn))
    except ModuleNotFoundError as exc:
        print(f"H84 snapshot validation failed: missing module {exc.name}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        # RuntimeErrors here are helper-owned, fixed validation messages; never
        # echo arbitrary database exceptions or connection strings.
        print(f"H84 snapshot validation failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # Exception text is restricted to avoid accidentally echoing DSNs.
        print(f"H84 snapshot validation failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
