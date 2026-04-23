"""tests/integration/test_email_collector.py
Phase 5 Task 1 — Email Collector integration tests (STEP 1.7)
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auth(client, tenant_id="test"):
    """Return headers with a valid test JWT for the given tenant."""
    import os, time, jwt
    secret = os.environ.get("JWT_SECRET", "test")
    token = jwt.encode(
        {"sub": "1", "type": "access", "email": "t@t.ge",
         "role": "admin", "tenant_id": tenant_id,
         "iat": int(time.time()), "exp": int(time.time()) + 3600},
        secret, algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


# ── STEP 1.6 routes ───────────────────────────────────────────────────────────

def test_email_collector_status_endpoint(client):
    """GET /email-collector/status → 200 with ok flag."""
    r = client.get("/email-collector/status", headers=_auth(client))
    assert r.status_code == 200
    data = r.json()
    assert "ok" in data
    assert "configured" in data


def test_email_collector_test_endpoint_bad_credentials(client):
    """POST /email-collector/test with bad creds → ok=False."""
    r = client.post(
        "/email-collector/test",
        json={"email": "bad@gmail.com", "app_password": "wrong"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert "error" in data


def test_email_collector_save_credentials_validates_first(client):
    """POST /email-collector/credentials tests IMAP before saving."""
    with patch(
        "app.api.routes_email_collector.test_imap_connection",
        return_value={"ok": False, "error": "auth failed"},
    ):
        r = client.post(
            "/email-collector/credentials",
            json={"email": "x@gmail.com", "app_password": "bad"},
            headers=_auth(client),
        )
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_email_collector_save_credentials_success(client):
    """POST /email-collector/credentials saves when IMAP OK."""
    with patch(
        "app.api.routes_email_collector.test_imap_connection",
        return_value={"ok": True},
    ), patch(
        "app.api.routes_email_collector.save_tenant_email_credentials",
        return_value=True,
    ):
        r = client.post(
            "/email-collector/credentials",
            json={"email": "real@gmail.com", "app_password": "xxxx xxxx xxxx xxxx"},
            headers=_auth(client),
        )
    assert r.status_code == 200
    assert r.json()["ok"] is True


# ── Tenant isolation ──────────────────────────────────────────────────────────

def test_email_collector_tenant_isolation(client):
    """Two tenants' status calls are independent."""
    with patch(
        "app.api.routes_email_collector.get_tenant_email_credentials",
        side_effect=lambda tid: {"email": f"{tid}@test.ge", "app_password": "x"} if tid == "tenant_a" else None,
    ):
        r_a = client.get("/email-collector/status", headers=_auth(client, "tenant_a"))
        r_b = client.get("/email-collector/status", headers=_auth(client, "tenant_b"))

    assert r_a.json()["configured"] is True
    assert r_b.json()["configured"] is False


# ── AI Processor draft creation ───────────────────────────────────────────────

@pytest.mark.anyio
async def test_ai_processor_creates_draft():
    """ai_process_document returns draft_id on success."""
    from app.api.services.ai_processor import ai_process_document

    mock_result = {
        "ok": True,
        "account_dr": "1210",
        "account_cr": "3310",
        "amount": 590.0,
        "description": "ინვოისი — Wolt",
        "confidence": 0.88,
        "_model": "claude-3-5-sonnet-20241022",
        "balance_payload": {"debit_account": "1210", "credit_account": "3310",
                            "amount": 590.0, "description": "ინვოისი — Wolt"},
    }

    with patch("app.api.services.ai_processor.build_ai_context", return_value={}), \
         patch("app.api.services.ai_processor._claude_analyze", new=AsyncMock(return_value=mock_result)), \
         patch("app.api.services.ai_processor._save_draft", return_value=42):

        result = await ai_process_document("test", 1, doc_text="ინვოისი Wolt 590 GEL")

    assert result["ok"] is True
    assert result["draft_id"] == 42
    assert result["status"] == "pending_human_review"


@pytest.mark.anyio
async def test_ai_processor_fallback_to_gemini():
    """ai_process_document falls back to Gemini when Claude raises."""
    from app.api.services.ai_processor import ai_process_document

    gemini_result = {
        "account_dr": "7510",
        "account_cr": "1121",
        "amount": 150.0,
        "description": "Facebook რეკლამა",
        "confidence": 0.75,
        "_model": "gemini-2.5-flash",
        "balance_payload": {},
    }

    with patch("app.api.services.ai_processor.build_ai_context", return_value={}), \
         patch("app.api.services.ai_processor._claude_analyze",
               new=AsyncMock(side_effect=RuntimeError("API key invalid"))), \
         patch("app.api.services.ai_processor._gemini_analyze",
               new=AsyncMock(return_value=gemini_result)), \
         patch("app.api.services.ai_processor._save_draft", return_value=99):

        result = await ai_process_document("test", 2, doc_text="Facebook advertising 150 GEL")

    assert result["ok"] is True
    assert result["model"] == "gemini-2.5-flash"


@pytest.mark.anyio
async def test_ai_processor_pending_review_status():
    """Draft must always be created with status=pending_human_review."""
    from app.api.services.ai_processor import ai_process_document

    valid_result = {
        "account_dr": "1120",
        "account_cr": "6110",
        "amount": 1000.0,
        "description": "test",
        "confidence": 0.9,
        "_model": "claude-3-5-sonnet-20241022",
        "balance_payload": {},
    }

    with patch("app.api.services.ai_processor.build_ai_context", return_value={}), \
         patch("app.api.services.ai_processor._claude_analyze",
               new=AsyncMock(return_value=valid_result)), \
         patch("app.api.services.ai_processor._save_draft", return_value=77):

        result = await ai_process_document("test", 3, doc_text="გადარიცხვა ABC Company-ზე 1000 GEL 2026-04-24")

    # The function must always return status=pending_human_review so approval UI can pick it up
    assert result.get("ok") is True
    assert result["status"] == "pending_human_review"
    assert result["draft_id"] == 77
