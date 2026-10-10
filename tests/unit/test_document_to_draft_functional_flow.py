"""Synthetic end-to-end route/service proof for document-to-review-draft flow."""

import asyncio
import json
import sys
import types
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import Response
from starlette.datastructures import UploadFile
from starlette.requests import Request

from app.api.db import tenant_db_context


FIXTURE = Path(__file__).parents[1] / "fixtures" / "document_to_draft" / "synthetic_invoice.txt"
INVOICE_BYTES = FIXTURE.read_bytes()
EXPECTED = {
    "document_number": "TEST-2026-0042",
    "issue_date": "2026-10-01",
    "net_amount": 120.00,
    "vat_amount": 24.00,
    "total_amount": 144.00,
    "seller_inn": "SELLER-TEST-ID",
    "buyer_inn": "BUYER-TEST-ID",
}


class MemoryRepository:
    """Small SQL-shaped fake for the real route/services; no DB driver/network."""

    def __init__(self):
        self.documents = {}
        self.drafts = {}
        self.tenants = {
            "tenant-alpha": {"company_inn": EXPECTED["buyer_inn"], "company_name_legal": "Alpha Synthetic LLC"},
            "tenant-beta": {"company_inn": EXPECTED["seller_inn"], "company_name_legal": "Beta Synthetic LLC"},
        }
        self.next_doc_id = 1
        self.next_draft_id = 1

    @asynccontextmanager
    async def connection(self):
        yield self

    async def fetchrow(self, sql, *args):
        normalized = " ".join(sql.split()).lower()
        if "from processed_documents where tenant_id" in normalized and "file_hash" in normalized:
            tenant_id, file_hash = args
            doc_id = self.documents.get((tenant_id, file_hash))
            if not doc_id:
                return None
            doc = self.documents[doc_id]
            return {"id": doc_id, "status": doc["status"],
                    "has_content": bool(doc.get("file_content") or doc.get("gcs_path"))}

        if "from journal_drafts where source_document_id" in normalized:
            source_id, tenant_id = args
            rows = [d for d in self.drafts.values()
                    if d["source_document_id"] == source_id and d["tenant_id"] == tenant_id]
            return {"id": rows[-1]["id"], "status": rows[-1]["status"]} if rows else None

        if "from journal_drafts where tenant_id" in normalized and "document_series" in normalized:
            tenant_id, series, number = args
            for draft in self.drafts.values():
                if (draft["tenant_id"] == tenant_id and draft.get("document_series") == series
                        and draft.get("document_number") == number and draft["status"] != "rejected"):
                    return {"id": draft["id"]}
            return None

        if "from tenants where tenant_id" in normalized:
            tenant_id = args[0]
            row = self.tenants.get(tenant_id)
            if not row:
                return None
            return {"company_inn": row["company_inn"], "company_name_legal": row["company_name_legal"],
                    "company_name_aliases": [], "owner_personal_id": None,
                    "company_type": "legal_entity", "is_vat_payer": True}

        if "from journal_drafts where id" in normalized and "tenant_id" in normalized:
            draft_id, tenant_id = args[:2]
            draft = self.drafts.get(draft_id)
            if not draft or draft["tenant_id"] != tenant_id:
                return None
            return dict(draft)

        if "from processed_documents where id" in normalized and "tenant_id" in normalized:
            doc_id, tenant_id = args[:2]
            doc = self.documents.get(doc_id)
            if not doc or doc["tenant_id"] != tenant_id:
                return None
            return dict(doc)

        raise AssertionError(f"Unexpected synthetic fetchrow query: {normalized}")

    async def fetchval(self, sql, *args):
        normalized = " ".join(sql.split()).lower()
        if normalized.startswith("insert into processed_documents"):
            tenant_id, file_hash, file_name, size, mime, file_content = args
            doc_id = self.next_doc_id
            self.next_doc_id += 1
            self.documents[(tenant_id, file_hash)] = doc_id
            self.documents[doc_id] = {
                "id": doc_id, "tenant_id": tenant_id, "file_hash": file_hash,
                "file_name": file_name, "file_size_bytes": size, "mime_type": mime,
                "file_content": file_content, "gcs_path": None, "status": "processing",
                "extraction_method": None, "raw_text": None, "extracted_data": None,
                "created_at": None,
            }
            return doc_id

        if normalized.startswith("update processed_documents set status = 'processing'"):
            doc_id, tenant_id = args
            doc = self.documents.get(doc_id)
            if doc and doc["tenant_id"] == tenant_id and doc["status"] == "failed":
                doc["status"] = "processing"
                return doc_id
            return None

        if normalized.startswith("select count(*) from journal_drafts"):
            tenant_id = args[0]
            return sum(1 for d in self.drafts.values() if d["tenant_id"] == tenant_id
                       and d["status"] in {"drafted", "pending_approval", "auto_approved", "pending_human_review"})

        raise AssertionError(f"Unexpected synthetic fetchval query: {normalized}")

    async def fetch(self, sql, *args):
        normalized = " ".join(sql.split()).lower()
        if "from journal_drafts" in normalized and "tenant_id" in normalized:
            tenant_id = args[0]
            return [dict(d) for d in self.drafts.values()
                    if d["tenant_id"] == tenant_id
                    and d["status"] in {"drafted", "pending_approval", "auto_approved", "pending_human_review"}]
        raise AssertionError(f"Unexpected synthetic fetch query: {normalized}")

    async def execute(self, sql, *args):
        normalized = " ".join(sql.split()).lower()
        if normalized.startswith("update journal_drafts set") and "where id = $2 and tenant_id = $3" in normalized:
            draft_id, tenant_id = args[-2:]
            draft = self.drafts.get(draft_id)
            if draft and draft["tenant_id"] == tenant_id:
                draft["description"] = args[0]
            return "UPDATE 1" if draft and draft["tenant_id"] == tenant_id else "UPDATE 0"

        if normalized.startswith("update processed_documents set raw_text"):
            raw_text, extraction_method, doc_id, tenant_id = args
            doc = self.documents.get(doc_id)
            if doc and doc["tenant_id"] == tenant_id:
                doc["raw_text"] = raw_text
                doc["extraction_method"] = extraction_method
            return "UPDATE 1"

        if normalized.startswith("update processed_documents set status"):
            status, doc_id, tenant_id = args
            doc = self.documents.get(doc_id)
            if doc and doc["tenant_id"] == tenant_id:
                doc["status"] = status
            return "UPDATE 1"

        if normalized.startswith("insert into journal_drafts"):
            if "is_foreign_doc" in normalized:
                (tenant_id, our_role, counterparty_inn, counterparty_name, series,
                 number, issue_date, amount, description, partner, reason,
                 debit_account, credit_account, raw_extraction, source_document_id,
                 journal_entries) = args
                draft_id = self.next_draft_id
                self.next_draft_id += 1
                self.drafts[draft_id] = {
                    "id": draft_id, "tenant_id": tenant_id, "status": "pending_human_review",
                    "our_role": our_role, "operation_type": "invoice",
                    "operation_category": None, "counterparty_inn": counterparty_inn,
                    "counterparty_name": counterparty_name, "document_series": series,
                    "document_number": number, "date": issue_date, "amount": amount,
                    "journal_entries": json.loads(journal_entries),
                    "raw_extraction": raw_extraction, "source_document_id": source_document_id,
                    "description": description, "confidence": None,
                    "debit_account": debit_account, "credit_account": credit_account,
                    "partner": partner, "currency": "GEL", "created_at": None,
                    "attached_file_name": None, "attached_file_path": None, "attached_file_size": None,
                }
                return "INSERT 0 1"
            (tenant_id, status, our_role, operation_type, category, counterparty_inn,
             counterparty_name, series, number, issue_date, amount, journal_entries,
             raw_extraction, source_document_id, description, confidence,
             debit_account, credit_account, partner) = args
            draft_id = self.next_draft_id
            self.next_draft_id += 1
            self.drafts[draft_id] = {
                "id": draft_id, "tenant_id": tenant_id, "status": status,
                "our_role": our_role, "operation_type": operation_type,
                "operation_category": category, "counterparty_inn": counterparty_inn,
                "counterparty_name": counterparty_name, "document_series": series,
                "document_number": number, "date": issue_date, "amount": amount,
                "journal_entries": json.loads(journal_entries),
                "raw_extraction": raw_extraction, "source_document_id": source_document_id,
                "description": description, "confidence": confidence,
                "debit_account": debit_account, "credit_account": credit_account,
                "partner": partner, "currency": "GEL", "created_at": None,
                "attached_file_name": None, "attached_file_path": None, "attached_file_size": None,
            }
            return "INSERT 0 1"

        raise AssertionError(f"Unexpected synthetic execute query: {normalized}")


def _request(tenant_id):
    request = Request({
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/synthetic-test",
        "raw_path": b"/synthetic-test",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "state": {},
    })
    request.state.authenticated = True
    request.state.role = "admin"
    request.state.tenant_id = tenant_id
    request.state.user_id = "synthetic-user"
    return request


def _invoice_extraction_json():
    return json.dumps({
        "document_type": "invoice",
        "document_series": "SYN",
        "document_number": EXPECTED["document_number"],
        "issue_date": EXPECTED["issue_date"],
        "seller": {"inn": EXPECTED["seller_inn"], "name": "Example Stationery Ltd"},
        "buyer": {"inn": EXPECTED["buyer_inn"], "name": "Example Customer"},
        "line_items": [{"description": "office supplies paper", "quantity": 1,
                        "amount_with_vat": EXPECTED["total_amount"], "vat_amount": EXPECTED["vat_amount"]}],
        "net_amount": EXPECTED["net_amount"],
        "total_vat": EXPECTED["vat_amount"],
        "total_with_vat": EXPECTED["total_amount"],
        "currency": "GEL",
    })


def test_real_route_service_flow_is_tenant_scoped_idempotent_and_reviewable(monkeypatch):
    from app.api import routes_documents, routes_approval, routes_posting
    from app.api.services import document_processing_service, approval_service, posting_preview_service

    repository = MemoryRepository()
    scheduled = []

    async def synthetic_parse(data, mime_type, llm_service=None):
        return {"text": INVOICE_BYTES.decode("utf-8"), "method": "synthetic_fixture"}

    class SyntheticLLM:
        async def complete(self, **_kwargs):
            return _invoice_extraction_json()

    def capture_task(coroutine):
        scheduled.append(coroutine)
        return SimpleNamespace(add_done_callback=lambda callback: None)

    async def upload_as(tenant_id):
        upload = UploadFile(filename="synthetic_invoice.txt", file=__import__("io").BytesIO(INVOICE_BYTES),
                            headers={"content-type": "text/plain"})
        async with tenant_db_context(tenant_id):
            response = await routes_documents.upload_document(upload, _request(tenant_id))
            if scheduled:
                await scheduled.pop(0)
        return response

    safe_llm_module = types.ModuleType("app.api.services.llm_service")
    safe_llm_module.llm_service = SyntheticLLM()

    async def synthetic_tenant(tenant_id):
        row = repository.tenants[tenant_id]
        return {"inn": row["company_inn"], "name": row["company_name_legal"], "aliases": [],
                "owner_personal_id": None, "company_type": "legal_entity", "is_vat_payer": True}

    from app.api.services import party_resolver
    with patch.object(routes_documents, "get_conn", repository.connection), \
         patch.object(document_processing_service, "get_conn", repository.connection), \
         patch.object(approval_service, "get_conn", repository.connection), \
         patch.object(posting_preview_service, "get_conn", repository.connection), \
         patch.object(party_resolver, "_load_tenant", side_effect=synthetic_tenant), \
         patch.object(routes_documents, "gcs_upload", return_value=None), \
         patch.object(routes_documents.asyncio, "create_task", side_effect=capture_task), \
         patch.object(document_processing_service, "parse_document", side_effect=synthetic_parse), \
         patch.object(document_processing_service, "_apply_completeness", return_value=None), \
         patch.object(document_processing_service, "_upsert_counterparty", return_value=None), \
         patch.dict(sys.modules, {"app.api.services.llm_service": safe_llm_module}):
        response_a = asyncio.run(upload_as("tenant-alpha"))
        response_b = asyncio.run(upload_as("tenant-beta"))

        doc_a = response_a["data"]["doc_id"]
        doc_b = response_b["data"]["doc_id"]
        draft_a = next(d for d in repository.drafts.values() if d["tenant_id"] == "tenant-alpha")
        draft_b = next(d for d in repository.drafts.values() if d["tenant_id"] == "tenant-beta")

        assert response_a["data"]["status"] == response_b["data"]["status"] == "processing"
        assert doc_a != doc_b
        for draft, doc_id, tenant_id in ((draft_a, doc_a, "tenant-alpha"), (draft_b, doc_b, "tenant-beta")):
            assert draft["tenant_id"] == tenant_id
            assert draft["source_document_id"] == doc_id
            assert draft["status"] == "pending_approval"
            assert draft["document_number"] == EXPECTED["document_number"]
            assert draft["date"] == EXPECTED["issue_date"]
            assert draft["amount"] == EXPECTED["total_amount"]
            assert draft["journal_entries"]  # established draft journal proposal, never ledger-posted

        # The same file retry in a tenant returns its existing draft and does not schedule work.
        retry = asyncio.run(upload_as("tenant-alpha"))
        assert retry["data"]["status"] == "duplicate_file"
        assert retry["data"]["existing_draft_id"] == draft_a["id"]
        assert not scheduled
        assert len([d for d in repository.drafts.values() if d["tenant_id"] == "tenant-alpha"]) == 1

        # Exercise the actual review-queue route/service and posting-preview API path.
        async def read_queue(tenant_id):
            async with tenant_db_context(tenant_id):
                return await routes_approval.get_queue(_request(tenant_id))

        queue_a = asyncio.run(read_queue("tenant-alpha"))
        queue_b = asyncio.run(read_queue("tenant-beta"))
        assert [d["id"] for d in queue_a["data"]["queue"]] == [draft_a["id"]]
        assert [d["id"] for d in queue_b["data"]["queue"]] == [draft_b["id"]]

        async def preview_as(tenant_id, draft_id):
            async with tenant_db_context(tenant_id):
                return await routes_posting.preview_posting(_request(tenant_id), draft_id)

        preview_a = asyncio.run(preview_as("tenant-alpha", draft_a["id"]))
        assert preview_a["draft"]["source_document_id"] == doc_a
        forbidden_preview = asyncio.run(preview_as("tenant-beta", draft_a["id"]))
        assert forbidden_preview["ok"] is False

        # The UI's source-document preview endpoint returns the synthetic attachment bytes.
        async def file_as(tenant_id, doc_id):
            async with tenant_db_context(tenant_id):
                return await routes_documents.get_document_file(doc_id, _request(tenant_id))

        file_response = asyncio.run(file_as("tenant-alpha", doc_a))
        assert isinstance(file_response, Response)
        assert file_response.body == INVOICE_BYTES
        denied_file = asyncio.run(file_as("tenant-beta", doc_a))
        assert denied_file.status_code == 404

        async def edit_as_other_tenant():
            from app.api.routes_approval import DraftUpdateRequest
            with patch.object(routes_approval, "get_conn", repository.connection):
                async with tenant_db_context("tenant-beta"):
                    return await routes_approval.update_draft(
                        draft_a["id"], DraftUpdateRequest(description="cross-tenant edit"), _request("tenant-beta")
                    )

        before_description = draft_a["description"]
        asyncio.run(edit_as_other_tenant())
        assert draft_a["description"] == before_description

        async def attach_as_other_tenant():
            from app.api import routes_approval
            upload = UploadFile(filename="synthetic.pdf", file=__import__("io").BytesIO(b"synthetic attachment"),
                                headers={"content-type": "application/pdf"})
            request = _request("tenant-beta")
            request.form = AsyncMock(return_value={"file": upload})
            with patch.object(routes_approval, "get_conn", repository.connection), \
                 patch("app.api.services.storage_service.upload_file") as upload_storage:
                async with tenant_db_context("tenant-beta"):
                    result = await routes_approval.attach_file_to_draft(draft_a["id"], request)
            assert getattr(result, "status_code", None) == 404, result
            upload_storage.assert_not_called()

        asyncio.run(attach_as_other_tenant())

        assert "posting/preview/" in (Path(__file__).parents[2] / "static" / "drafts.html").read_text(encoding="utf-8")
        assert "'/documents/' + srcDocId + '/file'" in (Path(__file__).parents[2] / "static" / "drafts.html").read_text(encoding="utf-8")


def test_upload_without_authenticated_tenant_fails_before_storage_or_database(monkeypatch):
    from app.api.routes_documents import upload_document

    async def run():
        upload = UploadFile(filename="synthetic_invoice.txt", file=__import__("io").BytesIO(INVOICE_BYTES))
        with patch("app.api.routes_documents.gcs_upload", side_effect=AssertionError("storage called")), \
             patch("app.api.routes_documents.get_conn", side_effect=AssertionError("database called")):
            with pytest.raises(HTTPException) as exc:
                await upload_document(upload, _request(None))
        assert exc.value.status_code == 403
        assert exc.value.detail["error"] == "TENANT_REQUIRED"

    asyncio.run(run())


def test_extraction_failure_is_visible_as_failed_and_never_creates_draft():
    from app.api import routes_documents
    from app.api.services import document_processing_service

    repository = MemoryRepository()
    scheduled = []
    safe_llm_module = types.ModuleType("app.api.services.llm_service")
    safe_llm_module.llm_service = None

    async def failing_parse(data, mime_type, llm_service=None):
        raise ValueError("synthetic OCR failure")

    async def run():
        upload = UploadFile(filename="synthetic_invoice.txt", file=__import__("io").BytesIO(INVOICE_BYTES),
                            headers={"content-type": "text/plain"})
        def capture(coroutine):
            scheduled.append(coroutine)
            return SimpleNamespace(add_done_callback=lambda callback: None)
        with patch.object(routes_documents, "get_conn", repository.connection), \
             patch.object(document_processing_service, "get_conn", repository.connection), \
             patch.object(routes_documents, "gcs_upload", return_value=None), \
             patch.object(routes_documents.asyncio, "create_task", side_effect=capture), \
             patch.object(document_processing_service, "parse_document", side_effect=failing_parse), \
             patch.dict(sys.modules, {"app.api.services.llm_service": safe_llm_module}):
            async with tenant_db_context("tenant-alpha"):
                queued = await routes_documents.upload_document(upload, _request("tenant-alpha"))
                await scheduled.pop(0)
                doc_id = queued["data"]["doc_id"]
                meta = await routes_documents.get_document_meta(doc_id, _request("tenant-alpha"))
        assert repository.documents[doc_id]["status"] == "failed"
        assert meta["data"]["status"] == "failed"
        assert "extraction failed" in meta["data"]["processing_message"].lower()
        assert repository.drafts == {}

    asyncio.run(run())


def test_retry_of_document_number_duplicate_returns_explicit_conflict():
    from app.api import routes_documents

    repository = MemoryRepository()
    file_hash = __import__("hashlib").sha256(INVOICE_BYTES).hexdigest()
    repository.documents[("tenant-alpha", file_hash)] = 7
    repository.documents[7] = {
        "id": 7, "tenant_id": "tenant-alpha", "file_hash": file_hash,
        "file_name": "synthetic_invoice.txt", "file_size_bytes": len(INVOICE_BYTES),
        "mime_type": "text/plain", "file_content": INVOICE_BYTES, "gcs_path": None,
        "status": "duplicate",
    }

    async def run():
        upload = UploadFile(filename="synthetic_invoice.txt", file=__import__("io").BytesIO(INVOICE_BYTES),
                            headers={"content-type": "text/plain"})
        with patch.object(routes_documents, "get_conn", repository.connection):
            async with tenant_db_context("tenant-alpha"):
                response = await routes_documents.upload_document(upload, _request("tenant-alpha"))
        assert response.status_code == 409
        assert json.loads(response.body)["error"]["code"] == "DUPLICATE_DOCUMENT"
        assert repository.drafts == {}

    asyncio.run(run())
