"""tests/integration/conftest.py — Shared fixtures for GeoTrade BIZ-1 integration tests.

All tests run with: JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL=""
DB connections are mocked via unittest.mock.patch.
No real database. No live RS.ge. No production credentials.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Company / tenant constants
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_tenant_id():
    return "geotrade_test"


@pytest.fixture(scope="session")
def own_company_inn():
    return "400000001"


# ---------------------------------------------------------------------------
# User mocks
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_user_viewer():
    user = MagicMock()
    user.role = "viewer"
    user.user_id = "viewer-001"
    user.tenant_id = "geotrade_test"
    return user


@pytest.fixture
def mock_user_accountant():
    user = MagicMock()
    user.role = "accountant"
    user.user_id = "accountant-001"
    user.tenant_id = "geotrade_test"
    return user


@pytest.fixture
def mock_user_admin():
    user = MagicMock()
    user.role = "admin"
    user.user_id = "admin-001"
    user.tenant_id = "geotrade_test"
    return user


@pytest.fixture
def mock_user_unauthorized():
    user = MagicMock()
    user.role = "external"
    user.user_id = "ext-001"
    user.tenant_id = "other_tenant"
    return user


# ---------------------------------------------------------------------------
# Mock DB
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db_conn():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    return conn


@pytest.fixture
def mock_pool(mock_db_conn):
    pool = AsyncMock()
    pool.acquire = AsyncMock(return_value=mock_db_conn)
    return pool


# ---------------------------------------------------------------------------
# JWT (sample, not real production secret)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sample_jwt():
    return "test.jwt.token"


# ---------------------------------------------------------------------------
# Fixture loaders
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def geotrade_fixtures():
    """Load all geotrade fixtures at once."""
    data = {}
    fixture_names = [
        "geotrade_opening_balances",
        "geotrade_rsge_documents",
        "geotrade_rsge_waybills",
        "geotrade_cash_register",
        "geotrade_payroll",
        "geotrade_fixed_assets",
        "geotrade_inventory_layers",
        "geotrade_expected_trial_balance",
        "geotrade_expected_profit_loss",
        "geotrade_expected_balance_sheet",
        "geotrade_expected_cashflow",
        "geotrade_expected_vat_report",
        "geotrade_expected_ar_ap_aging",
        "geotrade_expected_cfo_dashboard",
    ]
    for name in fixture_names:
        path = FIXTURES_DIR / f"{name}.json"
        with open(path, encoding="utf-8") as f:
            data[name] = json.load(f)
    return data


@pytest.fixture(scope="session")
def opening_balances_fixture(geotrade_fixtures):
    return geotrade_fixtures["geotrade_opening_balances"]


@pytest.fixture(scope="session")
def rsge_documents_fixture(geotrade_fixtures):
    return geotrade_fixtures["geotrade_rsge_documents"]


@pytest.fixture(scope="session")
def rsge_waybills_fixture(geotrade_fixtures):
    return geotrade_fixtures["geotrade_rsge_waybills"]


@pytest.fixture(scope="session")
def payroll_fixture(geotrade_fixtures):
    return geotrade_fixtures["geotrade_payroll"]


@pytest.fixture(scope="session")
def fixed_assets_fixture(geotrade_fixtures):
    return geotrade_fixtures["geotrade_fixed_assets"]


@pytest.fixture(scope="session")
def inventory_fixture(geotrade_fixtures):
    return geotrade_fixtures["geotrade_inventory_layers"]


@pytest.fixture(scope="session")
def trial_balance_fixture(geotrade_fixtures):
    return geotrade_fixtures["geotrade_expected_trial_balance"]


@pytest.fixture(scope="session")
def profit_loss_fixture(geotrade_fixtures):
    return geotrade_fixtures["geotrade_expected_profit_loss"]


@pytest.fixture(scope="session")
def balance_sheet_fixture(geotrade_fixtures):
    return geotrade_fixtures["geotrade_expected_balance_sheet"]


@pytest.fixture(scope="session")
def vat_report_fixture(geotrade_fixtures):
    return geotrade_fixtures["geotrade_expected_vat_report"]


@pytest.fixture(scope="session")
def aging_fixture(geotrade_fixtures):
    return geotrade_fixtures["geotrade_expected_ar_ap_aging"]


@pytest.fixture(scope="session")
def cfo_dashboard_fixture(geotrade_fixtures):
    return geotrade_fixtures["geotrade_expected_cfo_dashboard"]


@pytest.fixture(scope="session")
def bank_csv_fixture():
    path = FIXTURES_DIR / "geotrade_bank_statement.csv"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def cash_register_fixture(geotrade_fixtures):
    return geotrade_fixtures["geotrade_cash_register"]


# ---------------------------------------------------------------------------
# Helper: load specific RS.ge document by ID
# ---------------------------------------------------------------------------

@pytest.fixture
def rsge_fixture_loader(rsge_documents_fixture):
    def _load(doc_id: str):
        for doc in rsge_documents_fixture["documents"]:
            if doc["id"] == doc_id:
                return doc
        raise KeyError(f"RS.ge fixture doc not found: {doc_id}")
    return _load


@pytest.fixture
def bank_csv_fixture_loader(bank_csv_fixture):
    def _load():
        return bank_csv_fixture
    return _load


@pytest.fixture
def expected_report_loader(geotrade_fixtures):
    def _load(report_name: str):
        key = f"geotrade_expected_{report_name}"
        if key not in geotrade_fixtures:
            raise KeyError(f"Expected report fixture not found: {key}")
        return geotrade_fixtures[key]
    return _load
