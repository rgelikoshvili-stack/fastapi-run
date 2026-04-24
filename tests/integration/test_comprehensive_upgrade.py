"""
tests/integration/test_comprehensive_upgrade.py
Verifies all Phase 1-5 upgrade changes work correctly.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


# ── helpers ──────────────────────────────────────────────────────────────────

def _auth_headers(client, email="test@bridge.hub", tenant="default"):
    try:
        r = client.post("/auth/login", json={"email": email, "password": "testpass123", "tenant_id": tenant})
        token = (r.json().get("data") or {}).get("access_token", "")
    except Exception:
        token = ""
    return {"Authorization": f"Bearer {token}"} if token else {}


# ── TASK 1.1 — UUID cast ──────────────────────────────────────────────────────

def test_bank_accounts_list_no_uuid_error():
    """GET /bank-accounts/list must not 500 when tenant_id is 'default'."""
    from main import app
    client = TestClient(app, raise_server_exceptions=False)
    with patch("app.api.routes_bank_accounts.get_db") as mock_db:
        mock_cur = MagicMock()
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.return_value = []
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_db.return_value = mock_conn
        r = client.get("/bank-accounts/list")
    assert r.status_code != 500, f"Expected non-500, got {r.status_code}: {r.text[:200]}"


def test_budget_list_no_uuid_error():
    """GET /budget/list/{year} must not 500 when tenant_id is 'default'."""
    from main import app
    client = TestClient(app, raise_server_exceptions=False)
    with patch("app.api.routes_budget.get_db") as mock_db:
        mock_cur = MagicMock()
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.return_value = []
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_db.return_value = mock_conn
        r = client.get("/budget/list/2026")
    assert r.status_code != 500, f"Expected non-500, got {r.status_code}: {r.text[:200]}"


# ── TASK 2.2 — JournalEntryValidator ─────────────────────────────────────────

def test_validator_rejects_zero_amount():
    from app.api.services.journal_service import JournalEntryValidator
    with pytest.raises(ValueError, match="Amount"):
        JournalEntryValidator.validate_entry({"amount": 0, "account_code": "7510"})


def test_validator_rejects_invalid_code():
    from app.api.services.journal_service import JournalEntryValidator
    with pytest.raises(ValueError, match="account code"):
        JournalEntryValidator.validate_entry({"amount": 100, "account_code": "ETC"})


def test_validator_rejects_empty_code():
    from app.api.services.journal_service import JournalEntryValidator
    with pytest.raises(ValueError, match="account code"):
        JournalEntryValidator.validate_entry({"amount": 100, "account_code": "-"})


def test_validator_passes_valid_entry():
    from app.api.services.journal_service import JournalEntryValidator
    assert JournalEntryValidator.validate_entry({"amount": 100, "account_code": "7510"}) is True


# ── TASK 2.3 — Georgian INN validation ───────────────────────────────────────

def test_georgian_inn_valid_9():
    from app.api.services.journal_service import validate_georgian_inn
    assert validate_georgian_inn("202192643") is True


def test_georgian_inn_valid_11():
    from app.api.services.journal_service import validate_georgian_inn
    assert validate_georgian_inn("12345678901") is True


def test_georgian_inn_invalid_length():
    from app.api.services.journal_service import validate_georgian_inn
    assert validate_georgian_inn("1234") is False


def test_georgian_inn_invalid_chars():
    from app.api.services.journal_service import validate_georgian_inn
    assert validate_georgian_inn("20219264X") is False


# ── TASK 2.1 — resolve_account_code ──────────────────────────────────────────

def test_resolve_drops_etc():
    from app.api.services.document_extractor import resolve_account_code
    result = resolve_account_code("ETC", "bank fee commission")
    assert result == "7190"


def test_resolve_drops_dash():
    from app.api.services.document_extractor import resolve_account_code
    result = resolve_account_code("-", "salary payment")
    assert result == "7120"


def test_resolve_keeps_valid_code():
    from app.api.services.document_extractor import resolve_account_code
    result = resolve_account_code("6110", "anything")
    assert result == "6110"


# ── TASK 5.1 — /approval/stats ───────────────────────────────────────────────

_MOCK_TOKEN_PAYLOAD = {"sub": "test-user", "role": "admin", "tenant_id": "default", "type": "access"}


def test_approval_stats_endpoint_exists():
    from main import app
    client = TestClient(app, raise_server_exceptions=False)
    with patch("app.api.routes_approval.get_db") as mock_db, \
         patch("app.api.middleware.auth_middleware.verify_token", return_value=_MOCK_TOKEN_PAYLOAD):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = {
            "pending_count": 3, "auto_approved": 5,
            "manual_approved": 10, "rejected": 1, "avg_confidence": 0.85
        }
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_db.return_value = mock_conn
        r = client.get("/approval/stats", headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200
    data = r.json()
    assert "pending_count" in data


# ── TASK 5.1 — /approval/batch-action ────────────────────────────────────────

def test_batch_action_approve():
    from main import app
    client = TestClient(app, raise_server_exceptions=False)
    with patch("app.api.routes_approval.get_db") as mock_db, \
         patch("app.api.middleware.auth_middleware.verify_token", return_value=_MOCK_TOKEN_PAYLOAD):
        mock_cur = MagicMock()
        mock_cur.rowcount = 2
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_db.return_value = mock_conn
        r = client.post("/approval/batch-action",
                        json={"action": "approve", "draft_ids": [1, 2]},
                        headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True


def test_batch_action_invalid():
    from main import app
    client = TestClient(app, raise_server_exceptions=False)
    with patch("app.api.middleware.auth_middleware.verify_token", return_value=_MOCK_TOKEN_PAYLOAD):
        r = client.post("/approval/batch-action",
                        json={"action": "delete", "draft_ids": [1]},
                        headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is False


def test_batch_action_empty_ids():
    from main import app
    client = TestClient(app, raise_server_exceptions=False)
    with patch("app.api.middleware.auth_middleware.verify_token", return_value=_MOCK_TOKEN_PAYLOAD):
        r = client.post("/approval/batch-action",
                        json={"action": "approve", "draft_ids": []},
                        headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is False
