def test_invoice_ocr_fallback_import():
    from app.api.invoice_ocr_fallback import extract_text_with_ocr
    assert callable(extract_text_with_ocr)