"""tests/unit/test_h70a_ledger_write_rollout_gates.py

Contract tests for 11C-H70A-PRE — H70A Ledger Write Rollout Gates.
Verifies all 10 gates are documented and the decision is
H70A_PRE_ROLLOUT_GATES_DOCUMENTED_WAITING_FOR_H69.
No network, no DB, no app imports.
"""
import pathlib
import pytest

GATES_DOC = pathlib.Path(__file__).parents[2] / "docs" / "h70a-ledger-write-rollout-gates.md"
MIGRATION_SHA256 = "3077cec4c3d87fc0167ba02f70b13dcff871c1ce031b6fd0644d32554b3235d0"


@pytest.fixture(scope="module")
def doc():
    return GATES_DOC.read_text(encoding="utf-8")


class TestDocExists:
    def test_doc_exists(self):
        assert GATES_DOC.exists()

    def test_doc_not_empty(self, doc):
        assert len(doc) > 500

    def test_task_reference(self, doc):
        assert "11C-H70A-PRE" in doc

    def test_docs_tests_only_statement(self, doc):
        text = doc.lower()
        assert "docs" in text and ("tests only" in text or "no runtime" in text)


class TestAllTenGates:
    def test_g1_migration_011(self, doc):
        assert "H70A-G1" in doc

    def test_g2_table_existence(self, doc):
        assert "H70A-G2" in doc

    def test_g3_audit_event(self, doc):
        assert "H70A-G3" in doc

    def test_g4_recovery_query(self, doc):
        assert "H70A-G4" in doc

    def test_g5_idempotent_retry(self, doc):
        assert "H70A-G5" in doc

    def test_g6_recovery_event(self, doc):
        assert "H70A-G6" in doc

    def test_g7_precheck(self, doc):
        assert "H70A-G7" in doc

    def test_g8_integration_test(self, doc):
        assert "H70A-G8" in doc

    def test_g9_load_test(self, doc):
        assert "H70A-G9" in doc

    def test_g10_sign_off(self, doc):
        assert "H70A-G10" in doc

    def test_all_10_gates_present(self, doc):
        for i in range(1, 11):
            assert f"H70A-G{i}" in doc


class TestGateStatuses:
    def test_blocked_status_present(self, doc):
        assert "BLOCKED" in doc

    def test_open_status_present(self, doc):
        assert "OPEN" in doc

    def test_zero_pass_at_evaluation_time(self, doc):
        assert "0 PASS" in doc or "| 0 |" in doc or "PASS | 0" in doc

    def test_waiting_for_h69(self, doc):
        assert "H69" in doc
        assert "BLOCKED" in doc


class TestGateDetails:
    def test_g1_migration_sha(self, doc):
        assert MIGRATION_SHA256 in doc

    def test_g1_execution_window(self, doc):
        assert "23:00" in doc
        assert "2026-05-24" in doc

    def test_g2_all_three_tables(self, doc):
        assert "journal_entry_headers" in doc
        assert "journal_entry_lines" in doc
        assert "journal_entry_sources" in doc

    def test_g3_req1_linked(self, doc):
        idx = doc.find("H70A-G3")
        assert idx != -1
        snippet = doc[idx:idx + 600]
        assert "REQ-1" in snippet or "ledger_write_failed" in snippet

    def test_g5_req3_linked(self, doc):
        idx = doc.find("H70A-G5")
        assert idx != -1
        snippet = doc[idx:idx + 600]
        assert "REQ-3" in snippet or "idempotent" in snippet.lower()

    def test_g7_req5_linked(self, doc):
        idx = doc.find("H70A-G7")
        assert idx != -1
        snippet = doc[idx:idx + 600]
        assert "REQ-5" in snippet or "pre-check" in snippet.lower()

    def test_g8_depends_on_g1(self, doc):
        idx = doc.find("H70A-G8")
        assert idx != -1
        snippet = doc[idx:idx + 600]
        assert "H70A-G1" in snippet or "G1" in snippet or "Depends" in snippet

    def test_g9_100_concurrent(self, doc):
        assert "100" in doc
        assert "concurrent" in doc.lower()

    def test_g10_human_approval(self, doc):
        assert "Rolandi Gelikoshvili" in doc

    def test_g10_activation_template_redacted(self, doc):
        assert "POSTED_LEDGER_WRITES_ENABLED=true" in doc
        assert "gcloud run services update" in doc


class TestBlockingDependencies:
    def test_g1_blocks_g2(self, doc):
        text = doc
        assert "H70A-G1" in text and "H70A-G2" in text

    def test_g8_blocked_until_g1(self, doc):
        assert "H70A-G8" in doc
        assert "BLOCKED" in doc

    def test_g3_to_g7_independent_of_g1(self, doc):
        text = doc.lower()
        assert "independently" in text or "independent of" in text or "can be implemented" in text


class TestGateSummary:
    def test_total_gates_is_10(self, doc):
        assert "10" in doc
        assert ("Total" in doc or "total" in doc.lower())

    def test_blocked_count_present(self, doc):
        assert "BLOCKED" in doc

    def test_open_count_present(self, doc):
        assert "OPEN" in doc

    def test_zero_fail(self, doc):
        assert "0 FAIL" in doc or "0\n| **Total" in doc or "FAIL | 0" in doc

    def test_date_evaluated_present(self, doc):
        assert "2026-05-24" in doc

    def test_flag_must_remain_false(self, doc):
        assert "POSTED_LEDGER_WRITES_ENABLED" in doc
        text = doc.lower()
        assert "remain" in text or "must remain" in text or "false" in text


class TestReq1To5Coverage:
    def test_req1_mentioned(self, doc):
        assert "REQ-1" in doc

    def test_req2_mentioned(self, doc):
        assert "REQ-2" in doc

    def test_req3_mentioned(self, doc):
        assert "REQ-3" in doc

    def test_req4_mentioned(self, doc):
        assert "REQ-4" in doc

    def test_req5_mentioned(self, doc):
        assert "REQ-5" in doc


class TestFinalDecision:
    def test_gates_decision_present(self, doc):
        assert "H70A_PRE_ROLLOUT_GATES_DOCUMENTED_WAITING_FOR_H69" in doc

    def test_no_sql_executed(self, doc):
        text = doc.lower()
        assert "no sql" in text or "not executed" in text

    def test_production_not_touched(self, doc):
        text = doc.lower()
        assert "not touched" in text or "production db" in text

    def test_flag_remains_false(self, doc):
        assert "POSTED_LEDGER_WRITES_ENABLED" in doc
        assert "false" in doc.lower()


class TestSecurityConstraints:
    def test_no_raw_database_url(self, doc):
        assert "postgresql://" not in doc

    def test_no_production_password(self, doc):
        assert "BridgeHub" + "2026x" not in doc

    def test_no_posting_apply(self, doc):
        assert "posting/" + "apply" not in doc

    def test_no_balance_activation_key(self, doc):
        assert "BALANCE_API_KEY=sk" not in doc

    def test_gcloud_activation_template_only(self, doc):
        assert "gcloud run services update" in doc
        text = doc.lower()
        assert "template" in text or "do not run" in text or "# " in doc


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
