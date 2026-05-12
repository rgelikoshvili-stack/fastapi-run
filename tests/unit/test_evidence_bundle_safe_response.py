"""
tests/unit/test_evidence_bundle_safe_response.py

Tests ensuring future evidence bundle read responses are safe:
- Required fields are present.
- Secret-like keys are excluded.
- Nested unsafe keys are stripped.
- Connector response summary is safe.
- Event list metadata is safe.

Rules:
  - No real DB, no network, no connector calls.
  - Uses EvidenceBundleService.build_safe_response directly.
  - No route imports required.
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("TEST_MODE", "1")

from app.api.services.evidence_bundle_service import EvidenceBundleService, _strip_unsafe

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svc() -> EvidenceBundleService:
    from unittest.mock import MagicMock
    return EvidenceBundleService(MagicMock())


def _full_bundle(**overrides) -> dict:
    base = {
        "id": "eb-uuid-1",
        "tenant_id": "t1",
        "source_type": "bank_transaction",
        "source_id": "bt-42",
        "source_file_id": "file-1",
        "source_file_hash": "sha256:abc",
        "bank_transaction_id": "bt-42",
        "document_id": "doc-5",
        "ocr_result_id": "ocr-3",
        "journal_draft_id": "draft-10",
        "journal_entry_id": "entry-20",
        "approval_event_id": "appr-99",
        "posting_log_id": "log-55",
        "connector_provider": "balance",
        "connector_operation": "post_journal",
        "payload_preview_hash": "sha256:xyz",
        "ai_reasoning": {"model": "claude", "classification": "payroll"},
        "extracted_fields": {"amount": "1500.00", "currency": "GEL"},
        "risk_flags": ["HIGH_AMOUNT"],
        "confidence": 0.92,
        "status": "ready",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T01:00:00Z",
        "created_by": "user1",
        "updated_by": "user1",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# A) Required fields present in safe response
# ---------------------------------------------------------------------------

class TestSafeResponseIncludesRequiredFields:

    @pytest.mark.parametrize("field", [
        "id",
        "tenant_id",
        "source_type",
        "source_id",
        "source_file_hash",
        "ai_reasoning",
        "extracted_fields",
        "risk_flags",
        "confidence",
        "approval_event_id",
        "journal_draft_id",
        "journal_entry_id",
        "posting_log_id",
        "payload_preview_hash",
        "status",
    ])
    def test_required_field_present(self, field):
        svc = _svc()
        safe = svc.build_safe_response(_full_bundle())
        assert field in safe, f"Required field {field!r} missing from safe response"

    def test_source_type_value_preserved(self):
        svc = _svc()
        safe = svc.build_safe_response(_full_bundle())
        assert safe["source_type"] == "bank_transaction"

    def test_confidence_value_preserved(self):
        svc = _svc()
        safe = svc.build_safe_response(_full_bundle())
        assert safe["confidence"] == 0.92

    def test_status_value_preserved(self):
        svc = _svc()
        safe = svc.build_safe_response(_full_bundle())
        assert safe["status"] == "ready"

    def test_ai_reasoning_content_preserved(self):
        svc = _svc()
        safe = svc.build_safe_response(_full_bundle())
        assert safe["ai_reasoning"]["classification"] == "payroll"

    def test_risk_flags_preserved(self):
        svc = _svc()
        safe = svc.build_safe_response(_full_bundle())
        assert "HIGH_AMOUNT" in safe["risk_flags"]


# ---------------------------------------------------------------------------
# B) Secret-like keys excluded from top-level response
# ---------------------------------------------------------------------------

class TestSafeResponseExcludesSecretKeys:

    @pytest.mark.parametrize("secret_key", [
        "api_key",
        "password",
        "token",
        "secret",
        "encrypted_value",
        "raw_connector_payload",
        "raw_secret",
        "decrypted_value",
    ])
    def test_top_level_secret_excluded(self, secret_key):
        svc = _svc()
        bundle = _full_bundle(**{secret_key: "LEAKED_VALUE"})
        safe = svc.build_safe_response(bundle)
        assert secret_key not in safe, (
            f"Secret key {secret_key!r} must not appear in safe response"
        )

    def test_safe_response_body_string_has_no_leaked_values(self):
        svc = _svc()
        bundle = _full_bundle(
            api_key="LEAKED_API_KEY",
            password="LEAKED_PASSWORD",
            token="LEAKED_TOKEN",
        )
        safe = svc.build_safe_response(bundle)
        safe_str = str(safe)
        assert "LEAKED_API_KEY" not in safe_str
        assert "LEAKED_PASSWORD" not in safe_str
        assert "LEAKED_TOKEN" not in safe_str


# ---------------------------------------------------------------------------
# C) Nested unsafe keys stripped in JSONB fields
# ---------------------------------------------------------------------------

class TestNestedUnsafeKeysStripped:

    def test_ai_reasoning_strips_api_key(self):
        svc = _svc()
        bundle = _full_bundle(
            ai_reasoning={"model": "claude", "api_key": "SECRET", "result": "ok"}
        )
        safe = svc.build_safe_response(bundle)
        assert "api_key" not in safe["ai_reasoning"]
        assert safe["ai_reasoning"]["result"] == "ok"

    def test_ai_reasoning_strips_password(self):
        svc = _svc()
        bundle = _full_bundle(
            ai_reasoning={"model": "x", "password": "PASS"}
        )
        safe = svc.build_safe_response(bundle)
        assert "password" not in safe.get("ai_reasoning", {})

    def test_extracted_fields_strips_api_key(self):
        svc = _svc()
        bundle = _full_bundle(
            extracted_fields={"amount": "100", "api_key": "LEAK"}
        )
        safe = svc.build_safe_response(bundle)
        assert "api_key" not in safe["extracted_fields"]
        assert safe["extracted_fields"]["amount"] == "100"

    def test_extracted_fields_strips_encrypted_value(self):
        svc = _svc()
        bundle = _full_bundle(
            extracted_fields={"date": "2026-01-01", "encrypted_value": "ciphertext"}
        )
        safe = svc.build_safe_response(bundle)
        assert "encrypted_value" not in safe.get("extracted_fields", {})

    def test_deeply_nested_unsafe_stripped(self):
        svc = _svc()
        bundle = _full_bundle(
            ai_reasoning={
                "outer": {
                    "inner": {"api_key": "DEEP_LEAK", "ok": True}
                }
            }
        )
        safe = svc.build_safe_response(bundle)
        inner = safe["ai_reasoning"]["outer"]["inner"]
        assert "api_key" not in inner
        assert inner["ok"] is True


# ---------------------------------------------------------------------------
# D) Connector response summary safe
# ---------------------------------------------------------------------------

class TestConnectorResponseSummarySafe:

    def test_connector_provider_present_and_safe(self):
        svc = _svc()
        safe = svc.build_safe_response(_full_bundle())
        assert safe.get("connector_provider") == "balance"

    def test_connector_operation_present_and_safe(self):
        svc = _svc()
        safe = svc.build_safe_response(_full_bundle())
        assert safe.get("connector_operation") == "post_journal"

    def test_payload_preview_hash_present_not_body(self):
        svc = _svc()
        safe = svc.build_safe_response(_full_bundle())
        assert safe.get("payload_preview_hash") == "sha256:xyz"

    def test_raw_connector_payload_excluded(self):
        svc = _svc()
        bundle = _full_bundle(raw_connector_payload='{"amount": 9999}')
        safe = svc.build_safe_response(bundle)
        assert "raw_connector_payload" not in safe
        assert '{"amount": 9999}' not in str(safe)

    def test_connector_summary_has_no_credential_keys(self):
        svc = _svc()
        bundle = _full_bundle(
            ai_reasoning={"connector_response": {"status": "ok", "token": "LEAK"}}
        )
        safe = svc.build_safe_response(bundle)
        connector_resp = safe["ai_reasoning"].get("connector_response", {})
        assert "token" not in connector_resp
        assert connector_resp.get("status") == "ok"


# ---------------------------------------------------------------------------
# E) Event list safe
# ---------------------------------------------------------------------------

class TestEventListSafe:

    def test_strip_unsafe_on_event_metadata(self):
        events = [
            {"event_type": "approval_linked", "actor": "user1",
             "metadata": {"approval_event_id": "ae-1", "api_key": "LEAK"}},
            {"event_type": "posting_linked", "actor": "user1",
             "metadata": {"posting_log_id": "pl-1", "password": "PASS"}},
        ]
        safe_events = [_strip_unsafe(e) for e in events]
        assert "api_key" not in safe_events[0]["metadata"]
        assert safe_events[0]["metadata"]["approval_event_id"] == "ae-1"
        assert "password" not in safe_events[1]["metadata"]
        assert safe_events[1]["metadata"]["posting_log_id"] == "pl-1"

    def test_event_list_actors_preserved(self):
        events = [{"event_type": "created", "actor": "sysuser", "metadata": {}}]
        safe_events = [_strip_unsafe(e) for e in events]
        assert safe_events[0]["actor"] == "sysuser"


# ---------------------------------------------------------------------------
# F) None confidence handled safely
# ---------------------------------------------------------------------------

class TestNoneConfidence:

    def test_none_confidence_returned_as_none(self):
        svc = _svc()
        safe = svc.build_safe_response(_full_bundle(confidence=None))
        assert safe.get("confidence") is None

    def test_zero_confidence_returned_as_zero(self):
        svc = _svc()
        safe = svc.build_safe_response(_full_bundle(confidence=0.0))
        assert safe["confidence"] == 0.0


# ---------------------------------------------------------------------------
# G) No DB/network import in this test module
# ---------------------------------------------------------------------------

class TestNoDbNetworkInSafeResponseTest:

    def test_no_db_import_in_safe_response_test(self):
        import ast
        import pathlib
        src = pathlib.Path(
            "tests/unit/test_evidence_bundle_safe_response.py"
        ).read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "psycopg2" not in node.module
                assert "asyncpg" not in node.module
                assert "get_db" not in node.module
                assert "connector" not in node.module.lower()
