"""Smoke tests: Document Upload → Journal Drafts → Approval Queue workflow.

Tests run without DATABASE_URL (pure unit) — party resolution and INN matching logic.
"""
import pytest
from unittest.mock import patch, MagicMock

from app.api.services.document_extractor import ExtractedDocument, ExtractedParty
from app.api.services.party_resolver import resolve_party, OurRole

OUR_INN = "202192643"

_TENANT = {
    "inn": OUR_INN,
    "name": "ჩვენი კომპანია",
    "aliases": [],
    "owner_personal_id": None,
    "company_type": "legal_entity",
    "is_vat_payer": True,
}


def _make_doc(buyer_inn=None, seller_inn=None):
    return ExtractedDocument(
        seller=ExtractedParty(inn=seller_inn, name="გამყიდველი"),
        buyer=ExtractedParty(inn=buyer_inn, name="მყიდველი"),
        total_with_vat=1180.0,
        total_vat=180.0,
        net_amount=1000.0,
        issue_date="2026-04-27",
        currency="GEL",
    )


@pytest.fixture(autouse=True)
def mock_load_tenant():
    with patch("app.api.services.party_resolver._load_tenant", return_value=_TENANT):
        yield


# ── Smoke test 1: buyer_inn = ours → BUYER (purchase) ────────────────────────
def test_buyer_inn_matches_ours():
    doc = _make_doc(buyer_inn=OUR_INN, seller_inn="123456789")
    result = resolve_party(doc, "default")
    assert result.our_role == OurRole.BUYER, f"Expected BUYER, got {result.our_role}"
    assert result.counterparty_inn == "123456789"


# ── Smoke test 2: seller_inn = ours → SELLER (sale) ──────────────────────────
def test_seller_inn_matches_ours():
    doc = _make_doc(buyer_inn="987654321", seller_inn=OUR_INN)
    result = resolve_party(doc, "default")
    assert result.our_role == OurRole.SELLER, f"Expected SELLER, got {result.our_role}"
    assert result.counterparty_inn == "987654321"


# ── Smoke test 3: neither INN is ours → FOREIGN (pending_human_review) ───────
def test_foreign_document_blocked():
    doc = _make_doc(buyer_inn="111111111", seller_inn="222222222")
    result = resolve_party(doc, "default")
    assert result.our_role == OurRole.FOREIGN, f"Expected FOREIGN, got {result.our_role}"


# ── Smoke test 4: both INNs missing → FOREIGN ────────────────────────────────
def test_no_inns_is_foreign():
    doc = _make_doc(buyer_inn=None, seller_inn=None)
    result = resolve_party(doc, "default")
    assert result.our_role == OurRole.FOREIGN


# ── Smoke test 5: internal transfer ──────────────────────────────────────────
def test_both_sides_ours_is_internal():
    doc = _make_doc(buyer_inn=OUR_INN, seller_inn=OUR_INN)
    result = resolve_party(doc, "default")
    assert result.our_role == OurRole.INTERNAL
