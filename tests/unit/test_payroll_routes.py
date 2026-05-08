from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def test_payroll_report_endpoint_validates_filters(client):
    response = client.get("/reports/payroll?employee_id=abc-123&year=2026")

    assert response.status_code == 422
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_FILTER"


def test_payroll_report_endpoint_uses_tenant_scope(client):
    async def _fake_ledger(tenant_id, employee_id, year):
        return {
            "employee_id": employee_id,
            "year": year,
            "total_wages": 0,
            "count": 0,
            "lines": [],
            "tenant_id": tenant_id,
        }

    with patch("app.api.routes_reports.get_payroll_ledger", new=AsyncMock(side_effect=_fake_ledger)) as mock_ledger:
        response = client.get("/reports/payroll?employee_id=123456789&year=2026")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["tenant_id"] == "test"
    assert payload["data"]["employee_id"] == "123456789"
    assert payload["data"]["year"] == 2026
    mock_ledger.assert_awaited_once_with("test", "123456789", 2026)


def test_payroll_ledger_tenant_scoped(client):
    async def _fake_ledger(tenant_id, employee_id, year):
        return {
            "employee_id": employee_id,
            "year": year,
            "total_wages": 1200,
            "count": 1,
            "lines": [{"amount": 1200}],
        }

    with patch("app.api.routes_payroll.get_payroll_ledger", new=AsyncMock(side_effect=_fake_ledger)) as mock_ledger:
        response = client.get("/payroll/ledger?employee_id=123456789&year=2026")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["tenant_id"] == "test"
    assert payload["data"]["employee_id"] == "123456789"
    assert payload["data"]["year"] == 2026
    mock_ledger.assert_awaited_once_with("test", "123456789", 2026)


def test_payroll_filter_validation(client):
    response = client.get("/payroll/ledger?employee_id=abc-123&year=2026")

    assert response.status_code == 422
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_FILTER"


def test_payroll_runs_report_uses_tenant_scope(client):
    async def _fake_report(tenant_id, period):
        return {
            "period": period,
            "count": 1,
            "totals": {"gross": 1000, "pit": 200, "employee_pension": 20, "employer_pension": 20, "net": 780},
            "lines": [{"employee_name": "Nino", "gross_salary": 1000}],
        }

    with patch("app.api.routes_payroll.get_payroll_period_report", new=AsyncMock(side_effect=_fake_report)) as mock_report:
        response = client.get("/payroll/runs/report?period=2026-05")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["tenant_id"] == "test"
    assert payload["data"]["period"] == "2026-05"
    mock_report.assert_awaited_once_with("test", "2026-05")


def test_payroll_runs_report_validates_period(client):
    response = client.get("/payroll/runs/report?period=2026-13")

    assert response.status_code == 422
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_PERIOD"


def test_payroll_run_finalize_returns_approval_required(client):
    async def _fake_finalize(tenant_id, run_id):
        return {
            "id": run_id,
            "period": "2026-05",
            "status": "pending_approval",
            "drafts": {"ok": True, "draft_ids": [10, 11, 12, 13]},
        }

    with patch("app.api.routes_payroll.finalize_payroll_run", new=AsyncMock(side_effect=_fake_finalize)) as mock_finalize:
        response = client.post("/payroll/runs/7/finalize")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["approval_required"] is True
    assert payload["data"]["posted"] is False
    mock_finalize.assert_awaited_once_with("test", 7)


def test_payroll_unauthenticated_gets_401_or_403():
    from main import app

    unauthenticated = TestClient(app)
    response = unauthenticated.get("/payroll/runs")

    assert response.status_code in (401, 403)
