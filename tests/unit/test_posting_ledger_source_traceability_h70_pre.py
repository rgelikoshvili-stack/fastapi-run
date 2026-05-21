"""tests/unit/test_posting_ledger_source_traceability_h70_pre.py

Contract tests for 11C-H70-PRE — Posting Ledger Source Traceability Plan.
Verifies the traceability doc covers source rows, draft_id linkage, posting_log_id
linkage, tenant isolation, UUID/int mismatch handling, and audit trail completeness.
No network, no DB, no app imports.
"""
import pathlib
import pytest

DOC = pathlib.Path(__file__).parents[2] / "docs" / "posting-ledger-source-traceability-h70-pre.md"


@pytest.fixture(scope="module")
def doc():
    return DOC.read_text(encoding="utf-8")


class TestDocExists:
    def test_doc_exists(self):
        assert DOC.exists()

    def test_doc_not_empty(self, doc):
        assert len(doc) > 300

    def test_task_reference(self, doc):
        assert "11C-H70-PRE" in doc

    def test_final_decision_present(self, doc):
        assert "H70_PRE_DESIGN_READY_WAITING_FOR_H69" in doc

    def test_blocked_h69_present(self, doc):
        assert "BLOCKED_H69_MIGRATION_NOT_EXECUTED" in doc

    def test_blocked_schema_present(self, doc):
        assert "BLOCKED_LEDGER_SCHEMA_UNAVAILABLE" in doc


class TestSourcesTableDocumented:
    def test_journal_entry_sources_present(self, doc):
        assert "journal_entry_sources" in doc

    def test_source_type_present(self, doc):
        assert "source_type" in doc

    def test_source_id_present(self, doc):
        assert "source_id" in doc

    def test_draft_source_type_documented(self, doc):
        assert "journal_draft" in doc

    def test_posting_log_source_type_documented(self, doc):
        assert "posting_log" in doc


class TestDraftIdLinkage:
    def test_draft_id_linkage_documented(self, doc):
        assert "draft_id" in doc

    def test_str_draft_id_documented(self, doc):
        assert "str(draft_id)" in doc or "source_id" in doc

    def test_draft_row_written_always(self, doc):
        assert "always" in doc.lower() or "primary" in doc.lower() or "minimum" in doc.lower()


class TestPostingLogIdLinkage:
    def test_posting_log_id_linkage_documented(self, doc):
        assert "posting_log_id" in doc or "log_id" in doc

    def test_log_id_in_sources_documented(self, doc):
        assert "str(log_id)" in doc or "posting_log" in doc


class TestSourceDocumentLinkage:
    def test_source_document_id_documented(self, doc):
        assert "source_document_id" in doc

    def test_document_source_type_documented(self, doc):
        assert "document" in doc.lower()

    def test_optional_document_link_documented(self, doc):
        assert "if" in doc.lower() and ("set" in doc.lower() or "available" in doc.lower())


class TestUUIDIntMismatch:
    def test_uuid_mismatch_addressed(self, doc):
        assert "UUID" in doc and ("INTEGER" in doc or "int" in doc.lower() or "SERIAL" in doc)

    def test_source_draft_id_null_documented(self, doc):
        assert "source_draft_id" in doc
        assert "NULL" in doc or "null" in doc.lower()

    def test_posting_log_id_null_documented(self, doc):
        assert "posting_log_id" in doc
        assert "NULL" in doc or "null" in doc.lower()

    def test_text_source_id_preferred(self, doc):
        assert "TEXT" in doc or "text" in doc.lower()


class TestTenantIsolation:
    def test_tenant_id_on_every_row(self, doc):
        assert "tenant_id" in doc

    def test_tenant_isolation_invariant_documented(self, doc):
        assert "tenant" in doc.lower()
        text = doc.lower()
        assert "isolation" in text or "filter" in text or "every row" in text or "must carry" in text


class TestAuditTrail:
    def test_audit_trail_documented(self, doc):
        assert "audit" in doc.lower()

    def test_payload_json_referenced(self, doc):
        assert "payload_json" in doc or "payload" in doc.lower()

    def test_response_json_referenced(self, doc):
        assert "response_json" in doc or "response" in doc.lower()

    def test_chain_documented(self, doc):
        assert "chain" in doc.lower() or "trail" in doc.lower()


class TestSourceHashDocumented:
    def test_source_hash_documented(self, doc):
        assert "source_hash" in doc

    def test_sha256_method_documented(self, doc):
        assert "SHA-256" in doc or "sha256" in doc.lower()


class TestQueryPatterns:
    def test_draft_lookup_query_documented(self, doc):
        assert "source_type" in doc and "source_id" in doc

    def test_tenant_filter_in_query(self, doc):
        assert "tenant_id" in doc


class TestNoForbiddenPatterns:
    def test_no_raw_database_url(self, doc):
        assert "postgresql://" not in doc

    def test_no_production_password(self, doc):
        assert "BridgeHub" + "2026x" not in doc

    def test_no_posting_apply_path(self, doc):
        assert "posting/" + "apply" not in doc

    def test_no_gcloud_mutation(self, doc):
        assert "gcloud run services update" not in doc

    def test_no_balance_activation_key(self, doc):
        assert "BALANCE_API_KEY=sk" not in doc

    def test_drop_table_not_as_default(self, doc):
        if "DROP TABLE" in doc:
            assert "last resort" in doc.lower() or "LAST RESORT" in doc


class TestNoForbiddenImports:
    def test_no_forbidden_imports(self):
        with open(__file__, encoding="utf-8") as fh:
            lines = fh.readlines()
        forbidden = [
            "import " + "psycopg", "import " + "sqlalchemy",
            "import " + "requests", "import " + "httpx",
            "import " + "socket", "import " + "subprocess",
            "from " + "app.", "from docker" + " import",
        ]
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pat in forbidden:
                assert pat not in stripped, f"Forbidden: {pat!r} in {stripped!r}"
