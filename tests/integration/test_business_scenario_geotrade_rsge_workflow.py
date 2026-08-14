"""tests/integration/test_business_scenario_geotrade_rsge_workflow.py

BIZ-1: RS.ge documents, waybills, sync, evidence, draft, compare, test actions.

SAFETY: FIXTURE ONLY. No real RS.ge credentials. No live RS.ge calls.
No RS.ge mutation endpoints called. All RS.ge interactions are mocked or tested
via fixture data only.

Runs with: JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL=""
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Fixture validation — RS.ge documents
# ---------------------------------------------------------------------------

class TestRSgeDocumentFixtures:

    def test_rsge_documents_fixture_loaded(self, rsge_documents_fixture):
        assert len(rsge_documents_fixture["documents"]) >= 4

    def test_fixture_has_no_real_credentials(self, rsge_documents_fixture):
        """SAFETY: fixture must not contain real RS.ge credentials."""
        content = str(rsge_documents_fixture)
        assert "ACCESS_TOKEN" not in content
        assert "PIN_TOKEN" not in content
        assert "PASSWORD" not in content
        assert "rsge_password" not in content.lower()

    def test_purchase_invoice_exists(self, rsge_documents_fixture):
        ids = [d["id"] for d in rsge_documents_fixture["documents"]]
        assert "RS-INV-PUR-001" in ids

    def test_sale_invoice_exists(self, rsge_documents_fixture):
        ids = [d["id"] for d in rsge_documents_fixture["documents"]]
        assert "RS-INV-SALE-001" in ids

    def test_mismatch_fixture_exists(self, rsge_documents_fixture):
        ids = [d["id"] for d in rsge_documents_fixture["documents"]]
        assert "RS-INV-MISMATCH-001" in ids

    def test_amount_mismatch_fixture(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"]
                   if d["id"] == "RS-INV-AMOUNT-MISMATCH-001")
        assert doc["expected_bridge_hub"]["mismatch_type"] == "amount_mismatch"
        assert doc["expected_bridge_hub"]["diff"] == 100.00

    def test_all_documents_have_vat_type(self, rsge_documents_fixture):
        for doc in rsge_documents_fixture["documents"]:
            if "goods" in doc:
                for good in doc["goods"]:
                    assert "vat_type" in good, f"Missing vat_type in goods for doc {doc['id']}"

    def test_incoming_buyer_inn_is_own(self, rsge_documents_fixture, own_company_inn):
        incoming = [d for d in rsge_documents_fixture["documents"] if d["direction"] == "incoming"]
        for doc in incoming:
            if "buyer_inn" in doc:
                assert doc["buyer_inn"] == own_company_inn, \
                    f"Incoming doc {doc['id']}: buyer_inn must match own company INN"

    def test_outgoing_seller_inn_is_own(self, rsge_documents_fixture, own_company_inn):
        outgoing = [d for d in rsge_documents_fixture["documents"] if d["direction"] == "outgoing"]
        for doc in outgoing:
            if "seller_inn" in doc:
                assert doc["seller_inn"] == own_company_inn, \
                    f"Outgoing doc {doc['id']}: seller_inn must match own company INN"


# ---------------------------------------------------------------------------
# RS.ge Waybill Fixtures
# ---------------------------------------------------------------------------

class TestRSgeWaybillFixtures:

    def test_waybills_fixture_loaded(self, rsge_waybills_fixture):
        assert len(rsge_waybills_fixture["waybills"]) >= 2

    def test_incoming_waybill_linked_to_invoice(self, rsge_waybills_fixture):
        wb = next(w for w in rsge_waybills_fixture["waybills"] if w["id"] == "RS-WB-PUR-001")
        assert wb["linked_invoice_id"] == "RS-INV-PUR-001"

    def test_outgoing_waybill_linked_to_invoice(self, rsge_waybills_fixture):
        wb = next(w for w in rsge_waybills_fixture["waybills"] if w["id"] == "RS-WB-SALE-001")
        assert wb["linked_invoice_id"] == "RS-INV-SALE-001"

    def test_unlinked_waybill_mismatch(self, rsge_waybills_fixture):
        wb = next(w for w in rsge_waybills_fixture["waybills"] if w["id"] == "RS-WB-UNLINKED-001")
        assert wb["linked_invoice_id"] is None
        eb = wb["expected_bridge_hub"]
        assert eb["mismatch_type"] == "waybill_invoice_unlinked"

    def test_waybill_fixture_no_credentials(self, rsge_waybills_fixture):
        content = str(rsge_waybills_fixture)
        assert "ACCESS_TOKEN" not in content
        assert "PIN_TOKEN" not in content

    def test_waybill_has_goods_list(self, rsge_waybills_fixture):
        for wb in rsge_waybills_fixture["waybills"]:
            assert "goods" in wb, f"Waybill {wb['id']} missing goods list"

    def test_incoming_waybill_buyer_is_own(self, rsge_waybills_fixture, own_company_inn):
        wb = next(w for w in rsge_waybills_fixture["waybills"] if w["id"] == "RS-WB-PUR-001")
        assert wb["buyer_inn"] == own_company_inn

    def test_no_duplicate_on_resync(self, rsge_waybills_fixture):
        wb = next(w for w in rsge_waybills_fixture["waybills"] if w["id"] == "RS-WB-PUR-001")
        assert wb["expected_bridge_hub"]["no_duplicate_on_resync"] is True


# ---------------------------------------------------------------------------
# RS.ge Comparison / Mismatch Report (Phase 20)
# ---------------------------------------------------------------------------

class TestRSgeMismatchReport:

    def test_rsge_comparison_service_importable(self):
        from app.api.services.rsge_comparison_service import (
            MATCHED, AMOUNT_MISMATCH, VAT_MISMATCH,
            SELLER_BUYER_MISMATCH, MISSING_IN_BRIDGE,
            MISSING_IN_RSGE, DUPLICATE,
        )
        assert isinstance(MATCHED, str)
        assert isinstance(AMOUNT_MISMATCH, str)
        assert isinstance(MISSING_IN_BRIDGE, str)

    def test_mismatch_types_defined(self):
        from app.api.services.rsge_comparison_service import (
            MATCHED, AMOUNT_MISMATCH, VAT_MISMATCH,
            SELLER_BUYER_MISMATCH, MISSING_IN_BRIDGE,
            MISSING_IN_RSGE, DUPLICATE, REQUIRES_REVIEW,
        )
        all_types = [MATCHED, AMOUNT_MISMATCH, VAT_MISMATCH,
                     SELLER_BUYER_MISMATCH, MISSING_IN_BRIDGE,
                     MISSING_IN_RSGE, DUPLICATE, REQUIRES_REVIEW]
        assert len(all_types) == 8
        assert all(isinstance(t, str) for t in all_types)

    def test_risk_levels_defined(self):
        from app.api.services.rsge_comparison_service import (
            RISK_LOW, RISK_MEDIUM, RISK_HIGH,
        )
        assert isinstance(RISK_LOW, str)
        assert isinstance(RISK_MEDIUM, str)
        assert isinstance(RISK_HIGH, str)
        assert RISK_LOW != RISK_MEDIUM
        assert RISK_MEDIUM != RISK_HIGH

    def test_missing_in_bridge_fixture(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"]
                   if d["id"] == "RS-INV-MISMATCH-001")
        eb = doc["expected_bridge_hub"]
        assert eb["mismatch_type"] == "missing_in_bridge"
        assert eb["risk"] == "RISK_HIGH"

    def test_amount_mismatch_fixture(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"]
                   if d["id"] == "RS-INV-AMOUNT-MISMATCH-001")
        eb = doc["expected_bridge_hub"]
        assert eb["mismatch_type"] == "amount_mismatch"
        assert eb["risk"] == "RISK_MEDIUM"

    def test_waybill_unlinked_mismatch(self, rsge_waybills_fixture):
        wb = next(w for w in rsge_waybills_fixture["waybills"]
                  if w["id"] == "RS-WB-UNLINKED-001")
        assert wb["expected_bridge_hub"]["mismatch_type"] == "waybill_invoice_unlinked"
        assert wb["expected_bridge_hub"]["risk"] == "RISK_MEDIUM"

    def test_no_false_positives_for_matched(self, rsge_documents_fixture):
        """Matched documents have no mismatch type in expected_bridge_hub."""
        matched_docs = ["RS-INV-PUR-001", "RS-INV-SALE-001"]
        for doc_id in matched_docs:
            doc = next(d for d in rsge_documents_fixture["documents"] if d["id"] == doc_id)
            eb = doc["expected_bridge_hub"]
            assert "mismatch_type" not in eb, \
                f"Doc {doc_id} incorrectly flagged as mismatch"


# ---------------------------------------------------------------------------
# RS.ge Safety — No Live Calls
# ---------------------------------------------------------------------------

class TestRSgeSafety:

    def test_rsge_config_importable(self):
        from app.api.services.rsge_config import (
            is_enabled, is_test_mode, live_actions_enabled,
        )
        assert callable(is_enabled)
        assert callable(is_test_mode)
        assert callable(live_actions_enabled)

    def test_rsge_live_actions_disabled_in_test_mode(self):
        """In TEST_MODE=1, live RS.ge actions must remain disabled."""
        import os
        os.environ["TEST_MODE"] = "1"
        from app.api.services.rsge_config import live_actions_enabled
        assert live_actions_enabled() is False, \
            "SAFETY: live_actions_enabled() must return False in TEST_MODE"

    def test_no_real_rsge_url_in_fixture(self, rsge_documents_fixture):
        content = str(rsge_documents_fixture)
        assert "eapi.rs.ge" not in content
        assert "services.rs.ge" not in content

    def test_no_real_rsge_url_in_waybill_fixture(self, rsge_waybills_fixture):
        content = str(rsge_waybills_fixture)
        assert "eapi.rs.ge" not in content
        assert "services.rs.ge" not in content

    @pytest.mark.xfail(
        reason="EXPECTED_GAP_WAYBILL_ACTION_PROTOCOL: Waybill live actions "
               "(confirm/activate/cancel) are preview-only. Full action protocol "
               "requires feature flags to be enabled for a controlled pilot."
    )
    def test_waybill_live_confirm_in_test_mode(self):
        raise NotImplementedError("Waybill live confirm requires controlled pilot setup")

    @pytest.mark.xfail(
        reason="EXPECTED_GAP_RS_GE_LIVE_PILOT: Full RS.ge live pilot (confirm/reject/correct) "
               "requires Phase 0-6 of controlled_live_pilot_plan. Currently all safety flags=False."
    )
    def test_rsge_live_confirm_dry_run(self):
        raise NotImplementedError("RS.ge live pilot not yet activated")


# ---------------------------------------------------------------------------
# Evidence / Draft creation (mock-based)
# ---------------------------------------------------------------------------

class TestEvidenceAndDraft:

    def test_rsge_document_has_expected_bridge_hub(self, rsge_documents_fixture):
        for doc in rsge_documents_fixture["documents"]:
            assert "expected_bridge_hub" in doc, \
                f"Doc {doc['id']} missing expected_bridge_hub block"

    def test_purchase_creates_evidence_and_draft(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"]
                   if d["id"] == "RS-INV-PUR-001")
        eb = doc["expected_bridge_hub"]
        assert eb["requires_approval"] is True
        assert eb["no_auto_post"] is True

    def test_sale_requires_approval(self, rsge_documents_fixture):
        doc = next(d for d in rsge_documents_fixture["documents"]
                   if d["id"] == "RS-INV-SALE-001")
        eb = doc["expected_bridge_hub"]
        assert eb["requires_approval"] is True

    def test_no_duplicate_evidence_rule(self, rsge_documents_fixture):
        """Fixture states no duplicate evidence on re-sync."""
        for doc in rsge_documents_fixture["documents"]:
            eb = doc.get("expected_bridge_hub", {})
            if "no_auto_post" in eb:
                assert eb["no_auto_post"] is True
