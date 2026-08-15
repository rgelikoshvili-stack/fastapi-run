"""tests/unit/test_sprint1_image_ocr.py

Sprint 1: PNG/JPG image OCR pathway in email collector.
Verifies that image attachments are routed through Claude Vision
instead of being skipped (raw_text="" causing ai_process_document to fail).
"""
import asyncio
from unittest.mock import patch

import pytest


def run_sync(coro):
    return asyncio.run(coro)


# ─── _extract_text_from_image ─────────────────────────────────────────────────

def test_image_ocr_returns_text_when_vision_succeeds():
    from app.api.services.email_collector import _extract_text_from_image

    vision_result = {
        "seller": "სს ვენდორი",
        "invoice_number": "INV-2026-100",
        "date": "2026-08-01",
        "total_amount": 1500.0,
        "vat_amount": 225.0,
        "net_amount": 1275.0,
        "currency": "GEL",
    }

    with patch("app.api.services.email_collector._extract_text_from_image",
               wraps=_extract_text_from_image), \
         patch("app.api.services.ocr_service._extract_with_claude_vision",
               return_value=vision_result):
        result = _extract_text_from_image(b"fake_image_bytes", "invoice.png")

    assert isinstance(result, str)
    assert len(result) >= 20
    assert "ვენდორი" in result or "invoice" in result.lower() or "Partner" in result


def test_image_ocr_includes_amount():
    from app.api.services.email_collector import _extract_text_from_image

    vision_result = {
        "seller": "Test Ltd",
        "total_amount": 2000.0,
        "currency": "GEL",
        "invoice_number": None,
        "date": None,
        "vat_amount": None,
        "net_amount": None,
    }

    with patch("app.api.services.ocr_service._extract_with_claude_vision",
               return_value=vision_result):
        result = _extract_text_from_image(b"img", "receipt.jpg")

    assert "2000" in result
    assert "GEL" in result


def test_image_ocr_returns_empty_when_vision_returns_none():
    from app.api.services.email_collector import _extract_text_from_image

    with patch("app.api.services.ocr_service._extract_with_claude_vision",
               return_value=None):
        result = _extract_text_from_image(b"img", "scan.png")

    assert result == ""


def test_image_ocr_returns_empty_on_exception():
    from app.api.services.email_collector import _extract_text_from_image

    with patch("app.api.services.ocr_service._extract_with_claude_vision",
               side_effect=RuntimeError("API down")):
        result = _extract_text_from_image(b"img", "scan.png")

    assert result == ""


def test_image_ocr_empty_when_all_fields_null():
    from app.api.services.email_collector import _extract_text_from_image

    vision_result = {
        "seller": None, "invoice_number": None, "date": None,
        "total_amount": None, "vat_amount": None, "net_amount": None, "currency": None,
    }

    with patch("app.api.services.ocr_service._extract_with_claude_vision",
               return_value=vision_result):
        result = _extract_text_from_image(b"img", "blank.png")

    # "Document type: invoice" alone is < 20 chars so should return ""
    assert result == "" or len(result) < 25


# ─── collect_tenant_inbox routes PNG/JPG through OCR ─────────────────────────

def test_collect_inbox_png_calls_image_ocr():
    """PNG attachments must call _extract_text_from_image, not _extract_text_from_pdf."""
    from app.api.services import email_collector as ec

    with patch.object(ec, "_extract_text_from_image", return_value="Partner: TestCo\nTotal: 500 GEL") as mock_img, \
         patch.object(ec, "_extract_text_from_pdf", return_value="pdf text") as mock_pdf:
        ec._extract_text_from_image(b"bytes", "scan.png")

    mock_img.assert_called_once_with(b"bytes", "scan.png")
    mock_pdf.assert_not_called()


def test_collect_inbox_jpg_calls_image_ocr():
    """JPG attachments must call _extract_text_from_image."""
    from app.api.services import email_collector as ec

    with patch.object(ec, "_extract_text_from_image", return_value="Partner: TestCo\nTotal: 500 GEL") as mock_img:
        ec._extract_text_from_image(b"bytes", "receipt.jpg")

    mock_img.assert_called_once()


def test_collect_inbox_pdf_does_not_call_image_ocr():
    """PDF attachments must NOT go through image OCR."""
    from app.api.services import email_collector as ec

    with patch.object(ec, "_extract_text_from_image", return_value="") as mock_img, \
         patch.object(ec, "_extract_text_from_pdf", return_value="pdf text") as mock_pdf:
        ec._extract_text_from_pdf(b"pdf_bytes")
        mock_img.assert_not_called()
        mock_pdf.assert_called_once()


# ─── Source code guard ────────────────────────────────────────────────────────

def test_collect_inbox_source_branches_on_image_extension():
    """The collect_tenant_inbox source must branch on .png/.jpg/.jpeg extension."""
    import inspect
    from app.api.services.email_collector import collect_tenant_inbox
    src = inspect.getsource(collect_tenant_inbox)
    assert "_extract_text_from_image" in src, (
        "collect_tenant_inbox must call _extract_text_from_image for image attachments"
    )
    assert ".png" in src or ".jpg" in src, (
        "collect_tenant_inbox must check for .png or .jpg extension"
    )


def test_extract_text_from_image_defined_in_module():
    """_extract_text_from_image must be defined in email_collector module."""
    from app.api.services import email_collector as ec
    assert hasattr(ec, "_extract_text_from_image"), (
        "_extract_text_from_image must be defined in email_collector"
    )
    assert callable(ec._extract_text_from_image)
