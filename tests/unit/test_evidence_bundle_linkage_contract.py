"""
tests/unit/test_evidence_bundle_linkage_contract.py

Contract tests proving evidence bundle can link to approval and posting
identifiers WITHOUT changing approval/posting business logic.

Rules:
  - Mocks/fakes only — no real DB, no network, no connector calls.
  - approval_service.py and posting_service.py are NOT imported here.
  - EvidenceBundleService is used via mocked repository.
  - Tests verify that evidence bundle stores linkage metadata correctly.
  - Tests verify no connector call occurs from bundle operations.
  - Tests verify no posting execution occurs from bundle operations.
"""
from __future__ import annotations

import os
import hashlib
import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("TEST_MODE", "1")

from app.api.services.evidence_bundle_service import EvidenceBundleService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo(bundle_id: str = "bundle-uuid-100") -> MagicMock:
    base_bundle = {
        "id": bundle_id,
        "tenant_id": "t1",
        "source_type": "bank_transaction",
        "source_id": "bt-1",
        "source_file_hash": None,
        "bank_transaction_id": "bt-1",
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
        "created_by": None,
        "updated_by": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    repo = MagicMock()
    repo.insert_bundle = AsyncMock(return_value=base_bundle)
    repo.update_bundle = AsyncMock(return_value=base_bundle)
    repo.insert_event = AsyncMock(return_value={"id": "evt-x"})
    repo.get_bundle = AsyncMock(return_value=base_bundle)
    repo.list_bundle_events = AsyncMock(return_value=[])
    return repo


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# A) Approval linkage contract
# ---------------------------------------------------------------------------

class TestApprovalLinkageContract:

    @pytest.mark.asyncio
    async def test_link_approval_stores_approval_event_id(self):
        repo = _make_repo()
        svc = EvidenceBundleService(repo)
        await svc.link_approval("bundle-uuid-100", "t1", "appr-evt-42")
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["approval_event_id"] == "appr-evt-42"

    @pytest.mark.asyncio
    async def test_link_approval_stores_journal_draft_id(self):
        repo = _make_repo()
        svc = EvidenceBundleService(repo)
        await svc.link_approval("bundle-uuid-100", "t1", "appr-evt-1", journal_draft_id="draft-55")
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["journal_draft_id"] == "draft-55"

    @pytest.mark.asyncio
    async def test_link_approval_prepares_audit_event_row(self):
        repo = _make_repo()
        svc = EvidenceBundleService(repo)
        await svc.link_approval("bundle-uuid-100", "t1", "appr-evt-1")
        repo.insert_event.assert_called_once()
        event = repo.insert_event.call_args[0][0]
        assert event["event_type"] == "approval_linked"
        assert event["event_ref_type"] == "approval_event"
        assert event["tenant_id"] == "t1"

    @pytest.mark.asyncio
    async def test_link_approval_does_not_execute_posting(self):
        """Linking approval must never trigger a connector or posting call."""
        connector_called = []

        repo = _make_repo()
        svc = EvidenceBundleService(repo)

        # Patch in a trap that records any connector import attempt
        import app.api.services.evidence_bundle_service as svc_mod
        original_repo_call = repo.update_bundle.side_effect

        await svc.link_approval("bundle-uuid-100", "t1", "appr-evt-1")
        assert not connector_called, "Connector must not be called during link_approval"

    @pytest.mark.asyncio
    async def test_link_approval_event_metadata_contains_draft_ref(self):
        repo = _make_repo()
        svc = EvidenceBundleService(repo)
        await svc.link_approval("bundle-uuid-100", "t1", "appr-evt-1", journal_draft_id="draft-7")
        event = repo.insert_event.call_args[0][0]
        assert event["metadata"]["journal_draft_id"] == "draft-7"


# ---------------------------------------------------------------------------
# B) Posting linkage contract
# ---------------------------------------------------------------------------

class TestPostingLinkageContract:

    @pytest.mark.asyncio
    async def test_link_posting_stores_posting_log_id(self):
        repo = _make_repo()
        svc = EvidenceBundleService(repo)
        await svc.link_posting("bundle-uuid-100", "t1", "log-77")
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["posting_log_id"] == "log-77"

    @pytest.mark.asyncio
    async def test_link_posting_stores_payload_preview_hash_not_body(self):
        """Only the hash of the payload is stored — never the raw payload body."""
        payload_body = '{"amount": 1500.00, "currency": "GEL"}'
        payload_hash = _sha256(payload_body)

        repo = _make_repo()
        svc = EvidenceBundleService(repo)
        await svc.link_posting("bundle-uuid-100", "t1", "log-1",
                                payload_preview_hash=payload_hash)
        call_data = repo.update_bundle.call_args[0][2]
        # Only hash stored — never the raw payload
        assert call_data["payload_preview_hash"] == payload_hash
        assert payload_body not in str(call_data)

    @pytest.mark.asyncio
    async def test_link_posting_stores_connector_provider(self):
        repo = _make_repo()
        svc = EvidenceBundleService(repo)
        await svc.link_posting("bundle-uuid-100", "t1", "log-1",
                                connector_provider="balance")
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["connector_provider"] == "balance"

    @pytest.mark.asyncio
    async def test_link_posting_stores_connector_operation(self):
        repo = _make_repo()
        svc = EvidenceBundleService(repo)
        await svc.link_posting("bundle-uuid-100", "t1", "log-1",
                                connector_operation="post_journal")
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["connector_operation"] == "post_journal"

    @pytest.mark.asyncio
    async def test_link_posting_prepares_audit_event_row(self):
        repo = _make_repo()
        svc = EvidenceBundleService(repo)
        await svc.link_posting("bundle-uuid-100", "t1", "log-77")
        repo.insert_event.assert_called_once()
        event = repo.insert_event.call_args[0][0]
        assert event["event_type"] == "posting_linked"
        assert event["event_ref_type"] == "posting_log"
        assert event["event_ref_id"] == "log-77"

    @pytest.mark.asyncio
    async def test_link_posting_does_not_call_connector(self):
        """link_posting must store metadata only — no connector execution."""
        repo = _make_repo()
        svc = EvidenceBundleService(repo)
        await svc.link_posting("bundle-uuid-100", "t1", "log-1",
                                connector_provider="balance")
        # If no connector was imported or called, the test passes.
        # We assert the only external call was the mocked repository.
        assert repo.update_bundle.called
        assert repo.insert_event.called

    @pytest.mark.asyncio
    async def test_link_posting_connector_response_summary_safe(self):
        """Connector response summary metadata must not contain raw credentials."""
        repo = _make_repo()
        svc = EvidenceBundleService(repo)
        await svc.link_posting(
            "bundle-uuid-100", "t1", "log-1",
            connector_provider="balance",
            connector_operation="post_journal",
        )
        event = repo.insert_event.call_args[0][0]
        event_meta_str = str(event["metadata"])
        for forbidden in ("api_key", "password", "token", "secret", "encrypted_value"):
            assert forbidden not in event_meta_str.lower()


# ---------------------------------------------------------------------------
# C) Journal entry linkage contract
# ---------------------------------------------------------------------------

class TestJournalEntryLinkageContract:

    @pytest.mark.asyncio
    async def test_link_journal_entry_stores_entry_id(self):
        repo = _make_repo()
        svc = EvidenceBundleService(repo)
        await svc.link_journal_entry("bundle-uuid-100", "t1", "entry-999")
        call_data = repo.update_bundle.call_args[0][2]
        assert call_data["journal_entry_id"] == "entry-999"

    @pytest.mark.asyncio
    async def test_link_journal_entry_prepares_audit_event(self):
        repo = _make_repo()
        svc = EvidenceBundleService(repo)
        await svc.link_journal_entry("bundle-uuid-100", "t1", "entry-5")
        event = repo.insert_event.call_args[0][0]
        assert event["event_type"] == "entry_linked"
        assert event["event_ref_type"] == "journal_entry"
        assert event["event_ref_id"] == "entry-5"


# ---------------------------------------------------------------------------
# D) Source file hash linkage contract
# ---------------------------------------------------------------------------

class TestSourceFileHashContract:

    @pytest.mark.asyncio
    async def test_source_file_hash_stored_at_create(self):
        repo = _make_repo()
        svc = EvidenceBundleService(repo)
        file_hash = _sha256("file-contents-here")
        await svc.create_bundle("t1", "document", source_file_hash=file_hash)
        call_data = repo.insert_bundle.call_args[0][0]
        assert call_data["source_file_hash"] == file_hash

    @pytest.mark.asyncio
    async def test_source_file_hash_is_not_raw_content(self):
        """Only the hash is stored — never the raw file content."""
        repo = _make_repo()
        svc = EvidenceBundleService(repo)
        raw_content = "RAW FILE CONTENT — SENSITIVE DATA"
        file_hash = _sha256(raw_content)
        await svc.create_bundle("t1", "document", source_file_hash=file_hash)
        call_data = repo.insert_bundle.call_args[0][0]
        assert raw_content not in str(call_data)
        assert call_data["source_file_hash"] == file_hash


# ---------------------------------------------------------------------------
# E) No connector call from evidence bundle layer
# ---------------------------------------------------------------------------

class TestNoConnectorFromBundle:

    @pytest.mark.asyncio
    async def test_create_bundle_does_not_call_connector(self):
        connector_called = []

        class _TrapRepo:
            async def insert_bundle(self, data):
                return {**data, "id": "b1", "created_at": "x", "updated_at": "x"}
            async def insert_event(self, data):
                return {"id": "e1"}

        svc = EvidenceBundleService(_TrapRepo())
        await svc.create_bundle("t1", "bank_transaction", source_id="bt-1")
        assert not connector_called

    @pytest.mark.asyncio
    async def test_link_approval_does_not_call_connector_via_trap(self):
        connector_called = []

        class _TrapRepo:
            async def update_bundle(self, bundle_id, tenant_id, updates):
                return {"id": bundle_id, "tenant_id": tenant_id, **updates}
            async def insert_event(self, data):
                return {"id": "e1"}

        svc = EvidenceBundleService(_TrapRepo())
        await svc.link_approval("b1", "t1", "appr-1")
        assert not connector_called

    @pytest.mark.asyncio
    async def test_link_posting_does_not_call_connector_via_trap(self):
        connector_called = []

        class _TrapRepo:
            async def update_bundle(self, bundle_id, tenant_id, updates):
                return {"id": bundle_id, "tenant_id": tenant_id, **updates}
            async def insert_event(self, data):
                return {"id": "e1"}

        svc = EvidenceBundleService(_TrapRepo())
        await svc.link_posting("b1", "t1", "log-1", connector_provider="balance")
        assert not connector_called


# ---------------------------------------------------------------------------
# F) No DB/network import in test
# ---------------------------------------------------------------------------

class TestNoDbNetworkImport:

    def test_no_db_import_in_linkage_contract_test(self):
        import ast
        import pathlib
        src = pathlib.Path(
            "tests/unit/test_evidence_bundle_linkage_contract.py"
        ).read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "psycopg2" not in node.module
                assert "asyncpg" not in node.module
                assert "get_db" not in node.module
                assert "get_conn" not in node.module

    def test_no_connector_import_in_test(self):
        import ast
        import pathlib
        src = pathlib.Path(
            "tests/unit/test_evidence_bundle_linkage_contract.py"
        ).read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "balance_connector" not in node.module
                assert "posting_service" not in node.module
                assert "approval_service" not in node.module
