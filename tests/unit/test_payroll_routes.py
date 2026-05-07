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
