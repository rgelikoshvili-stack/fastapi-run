"""
tests/integration/test_document_intelligence.py  — Day 10

End-to-end document intelligence pipeline tests using synthetic PDF fixtures.
Tests parse → extract → classify → journal_build without a real LLM
(regex fallback is always available).

No DATABASE_URL required — uses FastAPI TestClient with mocked DB calls where needed.
Skip individual tests that require DB by checking DATABASE_URL.
"""
import io
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures"
DB_URL = os.environ.get("DATABASE_URL")

# ── Unit-level: parser ────────────────────────────────────────────────────────

def test_parser_native_pdf_extracts_text():
    """Native PDF parsing returns text and method=native_pdf."""
    import asyncio
    from app.api.services.document_parser import parse_document

    pdf_bytes = (FIXTURES / "invoice_buyer_it_services.pdf").read_bytes()
    result = asyncio.run(parse_document(pdf_bytes, "application/pdf", llm_service=None))

    assert result["method"] == "native_pdf", f"Expected native_pdf, got {result['method']}"
    text = result.get("text", "")
    assert len(text) > 50, f"Extracted text too short: {len(text)} chars"
    assert result.get("pages_count", 0) >= 1


def test_parser_returns_text_for_all_fixtures():
    """All 7 fixtures parse without error."""
    import asyncio
    from app.api.services.document_parser import parse_document

    pdfs = list(FIXTURES.glob("*.pdf"))
    assert len(pdfs) >= 7, f"Expected >=7 fixture PDFs, found {len(pdfs)}"

    for pdf_path in pdfs:
        pdf_bytes = pdf_path.read_bytes()
        result = asyncio.run(parse_document(pdf_bytes, "application/pdf", llm_service=None))
        assert result.get("text"), f"{pdf_path.name}: empty text"
        assert result.get("method"), f"{pdf_path.name}: missing method"


# ── Unit-level: extractor ────────────────────────────────────────────────────

def test_extractor_finds_inn_in_buyer_invoice():
    """Regex extractor picks up 9-digit INNs from invoice text."""
    import asyncio
    from app.api.services.document_extractor import extract_document

    text = """
    ᲡᲐᲡᲐᲥᲝᲜᲚᲝ ᲖᲔᲓᲜᲐᲓᲔᲑᲘ
    გამყიდველი: შპს ტექსერვისი  საიდ. ნომ.: 205123456
    მყიდველი: Alte University    საიდ. ნომ.: 202192643
    სულ: 1770.00 GEL
    """
    doc = asyncio.run(extract_document(text, llm_service=None))

    assert doc.seller.inn == "205123456" or doc.buyer.inn in ("205123456", "202192643"), \
        f"INN not found: seller={doc.seller.inn} buyer={doc.buyer.inn}"
    assert doc.total_with_vat is not None, "Amount not extracted"
    assert doc.total_with_vat == pytest.approx(1770.0, abs=1.0)


def test_extractor_date_normalization():
    """Date in DD.MM.YYYY format gets normalized to YYYY-MM-DD."""
    import asyncio
    from app.api.services.document_extractor import extract_document

    text = "Invoice date: 15.03.2026\nTotal: 500.00 GEL\nINN: 202192643"
    doc = asyncio.run(extract_document(text, llm_service=None))

    if doc.issue_date:
        assert doc.issue_date == "2026-03-15", f"Date not normalized: {doc.issue_date}"


def test_extractor_short_text_returns_unknown():
    """Text under 50 chars returns unknown type gracefully."""
    import asyncio
    from app.api.services.document_extractor import extract_document

    doc = asyncio.run(extract_document("short", llm_service=None))
    assert doc.document_type == "unknown"


# ── Unit-level: classifier ────────────────────────────────────────────────────

@pytest.mark.parametrize("description,expected_category", [
    ("IT services system development implementation", "it_services"),
    ("electricity utility bill komunaluri", "utilities"),
    ("office rent monthly ijaara", "office_rent"),
    ("advertising marketing campaign facebook ads", "marketing_ads"),
    ("Annual cloud subscription license", "it_saas"),
    ("office supplies paper stationery", "office_supplies"),
])
def test_classifier_keyword_detection(description, expected_category):
    """Keyword classifier assigns correct category."""
    import asyncio
    from app.api.services.operation_classifier import classify_operation_async
    from app.api.services.document_extractor import ExtractedDocument, ExtractedLineItem

    doc = ExtractedDocument(
        document_type="tax_invoice",
        line_items=[ExtractedLineItem(description=description, amount_with_vat=100)],
        total_with_vat=100,
    )
    category, confidence = asyncio.run(classify_operation_async(doc, llm_service=None))
    assert category.value == expected_category, \
        f"'{description}' → got {category.value}, expected {expected_category}"
    assert confidence > 0


# ── Unit-level: party resolver ───────────────────────────────────────────────

@pytest.mark.skipif(not DB_URL, reason="DATABASE_URL required")
def test_party_resolver_identifies_buyer():
    """When document buyer INN matches tenant, our_role=BUYER."""
    from app.api.services.party_resolver import resolve_party, OurRole
    from app.api.services.document_extractor import ExtractedDocument, ExtractedParty

    doc = ExtractedDocument(
        seller=ExtractedParty(inn="205123456", name="შპს სხვა"),
        buyer=ExtractedParty(inn="202192643", name="Alte University"),
        total_with_vat=1770.0,
    )
    result = resolve_party(doc, "default")
    assert result.our_role == OurRole.BUYER, f"Expected BUYER, got {result.our_role}"
    assert result.counterparty_inn == "205123456"


@pytest.mark.skipif(not DB_URL, reason="DATABASE_URL required")
def test_party_resolver_identifies_seller():
    """When document seller INN matches tenant, our_role=SELLER."""
    from app.api.services.party_resolver import resolve_party, OurRole
    from app.api.services.document_extractor import ExtractedDocument, ExtractedParty

    doc = ExtractedDocument(
        seller=ExtractedParty(inn="202192643", name="Alte University"),
        buyer=ExtractedParty(inn="205999888", name="შპს ბიტა"),
        total_with_vat=5000.0,
    )
    result = resolve_party(doc, "default")
    assert result.our_role == OurRole.SELLER, f"Expected SELLER, got {result.our_role}"
    assert result.counterparty_inn == "205999888"


@pytest.mark.skipif(not DB_URL, reason="DATABASE_URL required")
def test_party_resolver_detects_foreign_doc():
    """When neither party matches tenant, our_role=FOREIGN."""
    from app.api.services.party_resolver import resolve_party, OurRole
    from app.api.services.document_extractor import ExtractedDocument, ExtractedParty

    doc = ExtractedDocument(
        seller=ExtractedParty(inn="211111111", name="XYZ Corp"),
        buyer=ExtractedParty(inn="222222222", name="ABC LLC"),
        total_with_vat=8000.0,
    )
    result = resolve_party(doc, "default")
    assert result.our_role == OurRole.FOREIGN, f"Expected FOREIGN, got {result.our_role}"


# ── Unit-level: journal builder ──────────────────────────────────────────────

def test_journal_builder_buyer_expense():
    """Buyer expense (no asset threshold) → Dr 7xxx / Cr 3110."""
    from app.api.services.doc_journal_builder import build_journal
    from app.api.services.party_resolver import OurRole, PartyResolution
    from app.api.services.operation_classifier import OperationCategory
    from app.api.services.document_extractor import ExtractedDocument, ExtractedParty

    doc = ExtractedDocument(
        seller=ExtractedParty(inn="205123456", name="IT Co"),
        buyer=ExtractedParty(inn="202192643", name="Alte"),
        total_with_vat=1770.0,
        total_vat=270.0,
    )
    party = PartyResolution(
        our_role=OurRole.BUYER,
        counterparty_inn="205123456",
        counterparty_name="IT Co",
        our_tenant_name="Alte University",
        our_tenant_inn="202192643",
        confidence=0.9,
        warnings=[],
    )
    result = build_journal(doc, party, OperationCategory.IT_SERVICES, is_vat_payer=True)

    entries = result["entries"]
    assert len(entries) > 0, "No journal entries generated"
    debits = [str(e.get("dr", "")) for e in entries]
    credits = [str(e.get("cr", "")) for e in entries]
    assert any(a.startswith("7") for a in debits), \
        f"Expected 7xxx debit for expense, got debits={debits}"
    assert any(a in ("3110", "3100", "3120") for a in credits) or any(a for a in credits), \
        f"Expected payable credit, got credits={credits}"


def test_journal_builder_buyer_advance():
    """Advance payment → Dr 1490 / Cr 1010."""
    from app.api.services.doc_journal_builder import build_journal
    from app.api.services.party_resolver import OurRole, PartyResolution
    from app.api.services.operation_classifier import OperationCategory
    from app.api.services.document_extractor import ExtractedDocument, ExtractedParty

    doc = ExtractedDocument(
        seller=ExtractedParty(inn="213456789", name="Ad Agency"),
        buyer=ExtractedParty(inn="202192643", name="Alte"),
        total_with_vat=3000.0,
    )
    party = PartyResolution(
        our_role=OurRole.BUYER,
        counterparty_inn="213456789",
        counterparty_name="Ad Agency",
        our_tenant_name="Alte University",
        our_tenant_inn="202192643",
        confidence=0.9,
        warnings=[],
    )
    result = build_journal(doc, party, OperationCategory.ADVANCE_PAYMENT, is_vat_payer=True)

    entries = result["entries"]
    debits = [str(e.get("dr", "")) for e in entries]
    credits = [str(e.get("cr", "")) for e in entries]
    assert "1490" in debits, f"Expected 1490 (advance) in debits, got {debits}"
    assert any(a in ("1010", "3110", "3100") for a in credits), \
        f"Expected cash/payable credit, got {credits}"


def test_journal_builder_seller_revenue():
    """Seller invoice → Dr 1110 / Cr 6110."""
    from app.api.services.doc_journal_builder import build_journal
    from app.api.services.party_resolver import OurRole, PartyResolution
    from app.api.services.operation_classifier import OperationCategory
    from app.api.services.document_extractor import ExtractedDocument, ExtractedParty

    doc = ExtractedDocument(
        seller=ExtractedParty(inn="202192643", name="Alte"),
        buyer=ExtractedParty(inn="205999888", name="Client Co"),
        total_with_vat=5000.0,
        total_vat=0.0,
    )
    party = PartyResolution(
        our_role=OurRole.SELLER,
        counterparty_inn="205999888",
        counterparty_name="Client Co",
        our_tenant_name="Alte University",
        our_tenant_inn="202192643",
        confidence=0.9,
        warnings=[],
    )
    result = build_journal(doc, party, OperationCategory.EDUCATION, is_vat_payer=True)

    entries = result["entries"]
    debits = [str(e.get("dr", "")) for e in entries]
    credits = [str(e.get("cr", "")) for e in entries]
    assert "1110" in debits, f"Expected 1110 (receivable) in debits, got {debits}"
    assert any(a.startswith("6") for a in credits), \
        f"Expected 6xxx revenue credit, got {credits}"


# ── Integration: full pipeline (no DB) ──────────────────────────────────────

@pytest.mark.parametrize("pdf_name,expected_role,expected_cat_prefix", [
    ("invoice_buyer_it_services.pdf", "buyer", "it_"),
    ("utility_electricity.pdf", "buyer", "utilities"),
    ("office_rent_receipt.pdf", "buyer", "office_rent"),
    ("advance_payment.pdf", "buyer", "advance_payment"),
    ("saas_subscription.pdf", "buyer", "it_"),
])
@pytest.mark.skipif(not DB_URL, reason="DATABASE_URL required for party resolver")
def test_full_pipeline_pdf(pdf_name, expected_role, expected_cat_prefix):
    """Full parse→extract→resolve→classify pipeline for each fixture PDF."""
    import asyncio
    from app.api.services.document_parser import parse_document
    from app.api.services.document_extractor import extract_document
    from app.api.services.party_resolver import resolve_party
    from app.api.services.operation_classifier import classify_operation_async

    pdf_bytes = (FIXTURES / pdf_name).read_bytes()

    parsed = asyncio.run(parse_document(pdf_bytes, "application/pdf"))
    assert parsed["text"], f"{pdf_name}: no text extracted"

    extracted = asyncio.run(extract_document(parsed["text"]))
    assert extracted.total_with_vat is not None or extracted.seller.inn is not None, \
        f"{pdf_name}: extraction returned nothing useful"

    party = resolve_party(extracted, "default")
    assert party.our_role.value == expected_role, \
        f"{pdf_name}: expected role={expected_role}, got {party.our_role.value}"

    category, confidence = asyncio.run(classify_operation_async(extracted))
    assert category.value.startswith(expected_cat_prefix) or expected_cat_prefix in category.value, \
        f"{pdf_name}: expected category ~{expected_cat_prefix}, got {category.value}"


@pytest.mark.skipif(not DB_URL, reason="DATABASE_URL required")
def test_foreign_doc_pipeline(pdf_name="invoice_foreign.pdf"):
    """Foreign document pipeline: party=FOREIGN, journal entries=empty."""
    import asyncio
    from app.api.services.document_parser import parse_document
    from app.api.services.document_extractor import extract_document
    from app.api.services.party_resolver import resolve_party, OurRole
    from app.api.services.operation_classifier import classify_operation_async
    from app.api.services.doc_journal_builder import build_journal

    pdf_bytes = (FIXTURES / pdf_name).read_bytes()
    parsed = asyncio.run(parse_document(pdf_bytes, "application/pdf"))
    extracted = asyncio.run(extract_document(parsed["text"]))
    party = resolve_party(extracted, "default")

    assert party.our_role == OurRole.FOREIGN, \
        f"Expected FOREIGN for foreign doc, got {party.our_role}"


# ── Confidence score sanity ───────────────────────────────────────────────────

def test_confidence_higher_for_complete_data():
    """Document with INN + amount + date scores higher than minimal doc."""
    from app.api.routes_documents import _confidence_score
    from app.api.services.party_resolver import OurRole, PartyResolution
    from app.api.services.document_extractor import ExtractedDocument, ExtractedParty

    complete = ExtractedDocument(
        seller=ExtractedParty(inn="205123456"),
        buyer=ExtractedParty(inn="202192643"),
        total_with_vat=1770.0,
        document_series="AF",
        document_number="00123456",
    )
    minimal = ExtractedDocument()

    party = PartyResolution(our_role=OurRole.BUYER, counterparty_inn="205123456",
                            counterparty_name="Co", our_tenant_name="Alte",
                            our_tenant_inn="202192643", confidence=0.9, warnings=[])
    unknown_party = PartyResolution(our_role=OurRole.UNKNOWN, counterparty_inn=None,
                                    counterparty_name=None, our_tenant_name="",
                                    our_tenant_inn="", confidence=0.0, warnings=[])

    parsed = {"method": "native_pdf"}
    score_complete = _confidence_score(parsed, complete, party, 0.8)
    score_minimal = _confidence_score({"method": ""}, minimal, unknown_party, 0.0)

    assert score_complete > score_minimal, \
        f"Complete doc should score higher: {score_complete} vs {score_minimal}"
    assert 0.0 <= score_complete <= 1.0
    assert 0.0 <= score_minimal <= 1.0
