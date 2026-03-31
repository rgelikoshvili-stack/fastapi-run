def test_invoice_confidence_field():
    from app.api.invoice_parser import parse_invoice_pdf

    dummy = b"%PDF-1.4 test content"
    result = parse_invoice_pdf(dummy)

    assert "extraction_confidence" in result
    assert "review_required" in result