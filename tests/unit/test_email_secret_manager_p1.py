"""Email secret-source, test-mode, and redaction contracts."""
from __future__ import annotations

import asyncio
import inspect
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _safe_status_payload(payload):
    forbidden = ("password", "app_password", "smtp_pass", "imap_pass", "gmail_app_password")
    return not any(any(term in str(key).lower() for term in forbidden) for key in payload)


def test_missing_email_secret_is_degraded_without_crashing(monkeypatch):
    from app.api.email_service import send_email
    from app.api.services.email_invoice_service import get_email_status
    from app.config.secrets import get_email_secret

    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.delenv("TEST_SMTP_PASS", raising=False)
    monkeypatch.delenv("TEST_IMAP_PASS", raising=False)
    monkeypatch.setattr("app.api.email_service.SMTP_USER", "test-user@example.invalid")

    assert get_email_secret("SMTP_PASS") is None
    result = send_email("recipient@example.invalid", "test", "body")
    status = get_email_status()

    assert result["sent"] is False
    assert result["configured"] is False
    assert result["status"] == "degraded"
    assert status["configured"] is False
    assert status["status"] == "degraded"


def test_secret_value_is_never_logged_or_returned(monkeypatch, caplog):
    from app.api import email_service

    fake_secret = "fake-smtp-placeholder-123"
    monkeypatch.setenv("TEST_MODE", "0")
    monkeypatch.setattr(email_service, "SMTP_USER", "test-user@example.invalid")
    monkeypatch.setattr(email_service, "get_email_secret", lambda _name: fake_secret)
    server = MagicMock()
    server.__enter__.return_value = server
    server.login.side_effect = RuntimeError(f"provider echoed {fake_secret}")
    monkeypatch.setattr(email_service.smtplib, "SMTP", lambda *_args, **_kwargs: server)

    result = email_service.send_email("recipient@example.invalid", "test", "body")

    assert result == {
        "sent": False,
        "configured": True,
        "status": "degraded",
        "reason": "SMTP delivery failed",
    }
    assert fake_secret not in caplog.text
    assert fake_secret not in repr(result)


def test_status_and_api_contracts_never_include_password_fields():
    from app.api.services.email_invoice_service import get_email_status
    from app.api.routes_email_collector import email_collector_status

    status = get_email_status()
    source = inspect.getsource(email_collector_status).lower()

    assert _safe_status_payload(status)
    assert "app_password" not in source
    assert "smtp_pass" not in source
    assert "password" not in repr(status).lower()


def test_test_mode_accepts_only_explicit_fake_email_placeholders(monkeypatch):
    from app.config.secrets import get_email_secret
    from app.api.services import email_collector, email_invoice_service

    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("TEST_SMTP_PASS", "fake-smtp-placeholder")
    monkeypatch.setenv("SMTP_PASS", "must-not-be-read-in-test-mode")

    assert get_email_secret("SMTP_PASS") == "fake-smtp-placeholder"
    assert email_collector.test_imap_connection("fake@example.invalid", "fake-imap-placeholder")["mode"] == "test"
    with patch.object(email_invoice_service.imaplib, "IMAP4_SSL", side_effect=AssertionError("network path reached")):
        assert email_invoice_service.fetch_all_emails(tenant_id="tenant-test")["mode"] == "demo"
        assert email_invoice_service.process_email_by_id("1")["mode"] == "test"
        assert email_invoice_service.process_email_invoices()["mode"] == "test"

    monkeypatch.setenv("TEST_SMTP_PASS", "not-a-test-placeholder")
    assert get_email_secret("SMTP_PASS") is None


def test_secret_manager_loader_can_be_mocked(monkeypatch):
    from app.config import secrets

    monkeypatch.setenv("TEST_MODE", "0")
    monkeypatch.delenv("SMTP_PASS", raising=False)
    monkeypatch.setattr(secrets, "_USE_GSM", True)
    monkeypatch.setattr(secrets, "_fetch_from_gsm", lambda _secret_id: "test-gsm-placeholder")

    assert secrets.get_email_secret("SMTP_PASS") == "test-gsm-placeholder"


def test_cloud_run_secret_mapping_docs_use_names_not_secret_payloads():
    workflow = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    plan = (ROOT / "docs/p1_email_secret_manager_plan.md").read_text(encoding="utf-8")

    assert "--update-secrets" in workflow
    assert "SMTP_PASS=bridge-hub-smtp-password:latest" in workflow
    assert "IMAP_PASS=bridge-hub-imap-password:latest" in workflow
    assert "bridge-hub-smtp-password:latest" in plan
    assert "bridge-hub-imap-password:latest" in plan
    assert not re.search(r"(?i)(?:SMTP_PASS|IMAP_PASS)=\$\{\{\s*secrets\.[A-Z0-9_]+\}\}", workflow)


def test_env_example_has_no_email_secret_values():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert not re.search(r"(?im)^\s*(?:SMTP_PASS|GMAIL_APP_PASSWORD|IMAP_PASS|EMAIL_PASSWORD)\s*=\s*\S+", env_example)
    assert "injected from Google Secret Manager" in env_example


def test_deploy_workflow_uses_secret_refs_not_plaintext_email_passwords():
    workflow = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    assert "--set-secrets" not in workflow
    assert "--update-secrets" in workflow
    assert not re.search(r"SMTP_PASS=(?!bridge-hub-smtp-password:latest)[^,\\\"]+", workflow)
    assert not re.search(r"IMAP_PASS=(?!bridge-hub-imap-password:latest)[^,\\\"]+", workflow)
    assert "--update-env-vars" in workflow


def test_scoped_runtime_and_config_have_no_literal_email_password_assignments():
    paths = [
        ROOT / "app/api/email_service.py",
        ROOT / "app/api/services/email_collector.py",
        ROOT / "app/api/services/email_invoice_service.py",
        ROOT / "app/config/secrets.py",
        ROOT / ".env.example",
    ]
    literal_assignment = re.compile(
        r"(?im)^\s*(?:SMTP_PASS|GMAIL_APP_PASSWORD|APP_PASSWORD|IMAP_PASS|EMAIL_PASSWORD)\s*=\s*['\"][^'\"]+['\"]"
    )
    findings = []
    for path in paths:
        for match in literal_assignment.finditer(path.read_text(encoding="utf-8")):
            if "[stored-in-vault]" not in match.group(0):
                findings.append(str(path.relative_to(ROOT)))
    assert findings == []


@pytest.mark.asyncio
async def test_email_poller_imports_and_runs_without_real_credentials_in_test_mode(monkeypatch):
    from app.api.services import email_collector
    from app.startup import background

    captured = {}

    async def capture(_name, fn, interval):
        captured["run"] = fn

    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.delenv("TEST_IMAP_PASS", raising=False)
    with patch("app.startup.background._monitored_loop", side_effect=capture), \
         patch("app.startup.background.asyncio.sleep", new=AsyncMock()), \
         patch.object(email_collector, "get_all_active_tenants", new=AsyncMock(return_value=["tenant-test"])), \
         patch.object(email_collector, "get_tenant_email_credentials", new=AsyncMock(return_value=None)), \
         patch.object(email_collector.asyncio, "to_thread", new=AsyncMock(side_effect=AssertionError("network path reached"))):
        await background.email_poller_loop()
        result = await captured["run"]()

    assert result == {"total_processed": 0, "tenants": 1}
