"""
tests/unit/test_evidence_bundle_service.py

Unit tests for EvidenceBundleService.

Rules:
  - No real DB, no network, no connectors.
  - Repository fully mocked via AsyncMock.
  - No Balance.ge call.
  - Service imported; no runtime side-effects.
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("TEST_MODE", "1")

from app.api.services.evidence_bundle_service import EvidenceBundleService, _strip_unsafe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo(bundle_override: dict | None = None) -> MagicMock:
    """Return a fully-mocked repository."""
    bundle = bundle_override or {
        "id": "bundle-uuid-1",
        "tenant_id": "t1",
        "source_type": "bank_transaction",
        "source_id": "bt-42",
        "source_file_id": None,
        "source_file_hash": None,
        "bank_transaction_id": "bt-42",
        "document_id": None,
        "ocr_result_id": None,
        "journal_draft_id": None,
        "journal_entry_id": None,
        "approval_event_id": None,
        "posting_log_id": None,
        "connector_provider": None,
        "connector_operation": None,
        "payload_preview_hash": None,
        "ai_reasoning": {},
        "extracted_fields": {},
        "risk_flags": [],
        "confidence": None,
        "status": "draft",
        "created_by": "user1",
        "updated_by": "user1",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    repo = MagicMock()
    repo.insert_bundle = AsyncMock(return_value=bundle)
    repo.update_bundle = AsyncMock(return_value=bundle)
    repo.insert_event = AsyncMock(return_value={"id": "evt-1"})
    repo.get_bundle = AsyncMock(return_value=bundle)
    repo.list_bundle_events = AsyncMock(return_value=[])
    return repo


def _svc(repo=None) -> EvidenceBundleService:
    return EvidenceBundleService(repo or _make_repo())


# ---------------------------------------------------------------------------
# A) create_bundle
# ---------------------------------------------------------------------------

class TestCreateBundle:

    @pytest.mark.asyncio
    async def test_create_bundle_returns_bundle(self):
        svc = _svc()
        bundle = await svc.create_bundle("t1", "bank_transaction", source_id="bt-1")
        assert bundle["tenant_id"] == "t1"

    @pytest.mark.asyncio
    async def test_create_bundle_stores_source_type(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.create_bundle("t1", "bank_transaction", source_id="bt-1")
        call_kwargs = repo.insert_bundle.call_args[0][0]
        assert call_kwargs["source_type"] == "bank_transaction"

    @pytest.mark.asyncio
    async def test_create_bundle_stores_source_id(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.create_bundle("t1", "document", source_id="doc-99")
        call_kwargs = repo.insert_bundle.call_args[0][0]
        assert call_kwargs["source_id"] == "doc-99"

    @pytest.mark.asyncio
    async def test_create_bundle_stores_source_file_hash(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.create_bundle("t1", "document", source_file_hash="abc123")
        call_kwargs = repo.insert_bundle.call_args[0][0]
        assert call_kwargs["source_file_hash"] == "abc123"

    @pytest.mark.asyncio
    async def test_create_bundle_rejects_empty_tenant_id(self):
        svc = _svc()
        with pytest.raises(ValueError, match="tenant_id"):
            await svc.create_bundle("", "bank_transaction")

    @pytest.mark.asyncio
    async def test_create_bundle_rejects_blank_tenant_id(self):
        svc = _svc()
        with pytest.raises(ValueError, match="tenant_id"):
            await svc.create_bundle("   ", "bank_transaction")

    @pytest.mark.asyncio
    async def test_create_bundle_rejects_empty_source_type(self):
        svc = _svc()
        with pytest.raises(ValueError, match="source_type"):
            await svc.create_bundle("t1", "")

    @pytest.mark.asyncio
    async def test_create_bundle_calls_insert_event(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.create_bundle("t1", "bank_transaction")
        repo.insert_event.assert_called_once()
        event = repo.insert_event.call_args[0][0]
        assert event["event_type"] == "created"

    @pytest.mark.asyncio
    async def test_create_bundle_status_is_draft(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.create_bundle("t1", "bank_transaction")
        call_data = repo.insert_bundle.call_args[0][0]
        assert call_data["status"] == "draft"

    @pytest.mark.asyncio
    async def test_create_bundle_stores_bank_transaction_id(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.create_bundle("t1", "bank_transaction", bank_transaction_id="bt-7")
        call_data = repo.insert_bundle.call_args[0][0]
        assert call_data["bank_transaction_id"] == "bt-7"

    @pytest.mark.asyncio
    async def test_create_bundle_stores_document_id(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.create_bundle("t1", "document", document_id="doc-5")
        call_data = repo.insert_bundle.call_args[0][0]
        assert call_data["document_id"] == "doc-5"

    @pytest.mark.asyncio
    async def test_create_bundle_stores_ocr_result_id(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.create_bundle("t1", "ocr", ocr_result_id="ocr-99")
        call_data = repo.insert_bundle.call_args[0][0]
        assert call_data["ocr_result_id"] == "ocr-99"


# ---------------------------------------------------------------------------
# B) attach_ai_reasoning
# ---------------------------------------------------------------------------

class TestAttachAiReasoning:

    @pytest.mark.asyncio
    async def test_attach_ai_reasoning_stores_reasoning(self):
        repo = _make_repo()
        svc = _svc(repo)
        reasoning = {"model": "claude", "classification": "payroll"}
        await svc.attach_ai_reasoning("bundle-1", "t1", reasoning)
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["ai_reasoning"]["classification"] == "payroll"

    @pytest.mark.asyncio
    async def test_attach_ai_reasoning_stores_confidence(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.attach_ai_reasoning("bundle-1", "t1", {}, confidence=0.95)
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_attach_ai_reasoning_stores_risk_flags(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.attach_ai_reasoning("bundle-1", "t1", {}, risk_flags=["HIGH_AMOUNT"])
        call_data = repo.update_bundle.call_args[0][2]
        assert "HIGH_AMOUNT" in call_data["risk_flags"]

    @pytest.mark.asyncio
    async def test_confidence_too_high_rejected(self):
        svc = _svc()
        with pytest.raises(ValueError, match="confidence"):
            await svc.attach_ai_reasoning("b1", "t1", {}, confidence=1.1)

    @pytest.mark.asyncio
    async def test_confidence_negative_rejected(self):
        svc = _svc()
        with pytest.raises(ValueError, match="confidence"):
            await svc.attach_ai_reasoning("b1", "t1", {}, confidence=-0.1)

    @pytest.mark.asyncio
    async def test_confidence_zero_accepted(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.attach_ai_reasoning("b1", "t1", {}, confidence=0.0)
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_confidence_one_accepted(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.attach_ai_reasoning("b1", "t1", {}, confidence=1.0)
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_attach_ai_reasoning_calls_insert_event(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.attach_ai_reasoning("bundle-1", "t1", {"model": "x"})
        repo.insert_event.assert_called_once()
        event = repo.insert_event.call_args[0][0]
        assert event["event_type"] == "ai_attached"

    @pytest.mark.asyncio
    async def test_ai_reasoning_strips_unsafe_keys(self):
        repo = _make_repo()
        svc = _svc(repo)
        bad_reasoning = {"model": "x", "api_key": "SECRET", "reasoning": "ok"}
        await svc.attach_ai_reasoning("b1", "t1", bad_reasoning)
        call_data = repo.update_bundle.call_args[0][2]
        assert "api_key" not in call_data["ai_reasoning"]
        assert "reasoning" in call_data["ai_reasoning"]


# ---------------------------------------------------------------------------
# C) attach_extracted_fields
# ---------------------------------------------------------------------------

class TestAttachExtractedFields:

    @pytest.mark.asyncio
    async def test_attach_extracted_fields_stores_fields(self):
        repo = _make_repo()
        svc = _svc(repo)
        fields = {"amount": "1500.00", "currency": "GEL"}
        await svc.attach_extracted_fields("b1", "t1", fields)
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["extracted_fields"]["amount"] == "1500.00"

    @pytest.mark.asyncio
    async def test_attach_extracted_fields_strips_unsafe(self):
        repo = _make_repo()
        svc = _svc(repo)
        fields = {"amount": "100", "password": "HIDDEN"}
        await svc.attach_extracted_fields("b1", "t1", fields)
        call_data = repo.update_bundle.call_args[0][2]
        assert "password" not in call_data["extracted_fields"]

    @pytest.mark.asyncio
    async def test_attach_extracted_fields_calls_insert_event(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.attach_extracted_fields("b1", "t1", {"amount": "100"})
        repo.insert_event.assert_called_once()
        event = repo.insert_event.call_args[0][0]
        assert event["event_type"] == "fields_attached"


# ---------------------------------------------------------------------------
# D) link_approval
# ---------------------------------------------------------------------------

class TestLinkApproval:

    @pytest.mark.asyncio
    async def test_link_approval_stores_approval_event_id(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.link_approval("b1", "t1", "appr-evt-42")
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["approval_event_id"] == "appr-evt-42"

    @pytest.mark.asyncio
    async def test_link_approval_stores_journal_draft_id(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.link_approval("b1", "t1", "appr-evt-1", journal_draft_id="draft-7")
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["journal_draft_id"] == "draft-7"

    @pytest.mark.asyncio
    async def test_link_approval_calls_insert_event(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.link_approval("b1", "t1", "appr-evt-1")
        repo.insert_event.assert_called_once()
        event = repo.insert_event.call_args[0][0]
        assert event["event_type"] == "approval_linked"
        assert event["event_ref_id"] == "appr-evt-1"


# ---------------------------------------------------------------------------
# E) link_posting
# ---------------------------------------------------------------------------

class TestLinkPosting:

    @pytest.mark.asyncio
    async def test_link_posting_stores_posting_log_id(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.link_posting("b1", "t1", "log-55")
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["posting_log_id"] == "log-55"

    @pytest.mark.asyncio
    async def test_link_posting_stores_payload_hash(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.link_posting("b1", "t1", "log-1", payload_preview_hash="sha256:abc")
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["payload_preview_hash"] == "sha256:abc"

    @pytest.mark.asyncio
    async def test_link_posting_stores_connector_provider(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.link_posting("b1", "t1", "log-1", connector_provider="balance")
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["connector_provider"] == "balance"

    @pytest.mark.asyncio
    async def test_link_posting_calls_insert_event(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.link_posting("b1", "t1", "log-1")
        repo.insert_event.assert_called_once()
        event = repo.insert_event.call_args[0][0]
        assert event["event_type"] == "posting_linked"

    @pytest.mark.asyncio
    async def test_link_posting_event_ref_id_is_log_id(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.link_posting("b1", "t1", "log-77")
        event = repo.insert_event.call_args[0][0]
        assert event["event_ref_id"] == "log-77"


# ---------------------------------------------------------------------------
# F) link_journal_entry
# ---------------------------------------------------------------------------

class TestLinkJournalEntry:

    @pytest.mark.asyncio
    async def test_link_journal_entry_stores_entry_id(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.link_journal_entry("b1", "t1", "entry-200")
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["journal_entry_id"] == "entry-200"

    @pytest.mark.asyncio
    async def test_link_journal_entry_calls_insert_event(self):
        repo = _make_repo()
        svc = _svc(repo)
        await svc.link_journal_entry("b1", "t1", "entry-5")
        repo.insert_event.assert_called_once()
        event = repo.insert_event.call_args[0][0]
        assert event["event_type"] == "entry_linked"


# ---------------------------------------------------------------------------
# G) get_bundle
# ---------------------------------------------------------------------------

class TestGetBundle:

    @pytest.mark.asyncio
    async def test_get_bundle_delegates_to_repo(self):
        repo = _make_repo()
        svc = _svc(repo)
        result = await svc.get_bundle("b1", "t1")
        repo.get_bundle.assert_called_once_with("b1", "t1")
        assert result["id"] == "bundle-uuid-1"

    @pytest.mark.asyncio
    async def test_get_bundle_returns_none_when_not_found(self):
        repo = _make_repo()
        repo.get_bundle = AsyncMock(return_value=None)
        svc = _svc(repo)
        result = await svc.get_bundle("missing", "t1")
        assert result is None


# ---------------------------------------------------------------------------
# H) build_safe_response
# ---------------------------------------------------------------------------

class TestBuildSafeResponse:

    def test_safe_response_includes_standard_fields(self):
        svc = _svc()
        bundle = {
            "id": "uuid-1", "tenant_id": "t1", "source_type": "bank_transaction",
            "source_id": "bt-1", "source_file_hash": "sha256:x",
            "ai_reasoning": {"model": "claude"}, "extracted_fields": {"amount": "100"},
            "risk_flags": [], "confidence": 0.9, "status": "ready",
            "approval_event_id": "ae-1", "journal_draft_id": "d-1",
            "journal_entry_id": "e-1", "posting_log_id": "pl-1",
            "payload_preview_hash": "sha256:y",
        }
        safe = svc.build_safe_response(bundle)
        for field in ("id", "tenant_id", "source_type", "source_file_hash",
                      "ai_reasoning", "confidence", "status",
                      "approval_event_id", "journal_draft_id",
                      "journal_entry_id", "posting_log_id", "payload_preview_hash"):
            assert field in safe, f"Expected field {field!r} in safe response"

    def test_safe_response_excludes_api_key(self):
        svc = _svc()
        bundle = {"id": "u1", "tenant_id": "t1", "source_type": "x",
                  "api_key": "SECRET", "status": "draft"}
        safe = svc.build_safe_response(bundle)
        assert "api_key" not in safe

    def test_safe_response_excludes_password(self):
        svc = _svc()
        bundle = {"id": "u1", "tenant_id": "t1", "source_type": "x",
                  "password": "pass123", "status": "draft"}
        safe = svc.build_safe_response(bundle)
        assert "password" not in safe

    def test_safe_response_excludes_token(self):
        svc = _svc()
        bundle = {"id": "u1", "tenant_id": "t1", "source_type": "x",
                  "token": "tkn", "status": "draft"}
        safe = svc.build_safe_response(bundle)
        assert "token" not in safe

    def test_safe_response_excludes_encrypted_value(self):
        svc = _svc()
        bundle = {"id": "u1", "tenant_id": "t1", "source_type": "x",
                  "encrypted_value": "enc", "status": "draft"}
        safe = svc.build_safe_response(bundle)
        assert "encrypted_value" not in safe

    def test_safe_response_strips_nested_unsafe_in_ai_reasoning(self):
        svc = _svc()
        bundle = {"id": "u1", "tenant_id": "t1", "source_type": "x",
                  "ai_reasoning": {"model": "x", "api_key": "LEAK"},
                  "status": "draft"}
        safe = svc.build_safe_response(bundle)
        assert "api_key" not in safe.get("ai_reasoning", {})

    def test_safe_response_strips_nested_unsafe_in_extracted_fields(self):
        svc = _svc()
        bundle = {"id": "u1", "tenant_id": "t1", "source_type": "x",
                  "extracted_fields": {"amount": "100", "password": "PW"},
                  "status": "draft"}
        safe = svc.build_safe_response(bundle)
        assert "password" not in safe.get("extracted_fields", {})


# ---------------------------------------------------------------------------
# I) _strip_unsafe utility
# ---------------------------------------------------------------------------

class TestStripUnsafe:

    def test_strips_api_key(self):
        assert "api_key" not in _strip_unsafe({"api_key": "x", "model": "y"})

    def test_preserves_safe_keys(self):
        result = _strip_unsafe({"model": "x", "confidence": 0.9})
        assert result["model"] == "x"
        assert result["confidence"] == 0.9

    def test_strips_nested_api_key(self):
        result = _strip_unsafe({"outer": {"api_key": "x", "val": 1}})
        assert "api_key" not in result["outer"]

    def test_strips_in_list_of_dicts(self):
        result = _strip_unsafe([{"api_key": "x", "ok": True}])
        assert "api_key" not in result[0]

    def test_passes_through_non_dict_non_list(self):
        assert _strip_unsafe("hello") == "hello"
        assert _strip_unsafe(42) == 42
        assert _strip_unsafe(None) is None


# ---------------------------------------------------------------------------
# J) No DB/network imports in service module
# ---------------------------------------------------------------------------

class TestNoDbNetworkInService:

    def test_service_module_does_not_import_connector(self):
        import ast
        import pathlib
        src = pathlib.Path("app/api/services/evidence_bundle_service.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "connector" not in node.module.lower()
                assert "balance_connector" not in node.module.lower()
                assert "posting_service" not in node.module.lower()

    def test_repository_module_does_not_import_connector(self):
        import ast
        import pathlib
        src = pathlib.Path("app/api/services/evidence_bundle_repository.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "connector" not in node.module.lower()
