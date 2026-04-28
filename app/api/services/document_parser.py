"""app/api/services/document_parser.py
3-tier document text extraction:
  1. Native PDF (PyMuPDF / fitz)
  2. OCR (Tesseract kat+eng+rus)
  3. Vision LLM fallback
"""
import io
import re
import logging
from typing import Optional

log = logging.getLogger(__name__)

MIN_TEXT_QUALITY = 0.5
MIN_TEXT_LENGTH = 50


def _is_good_text(text: str) -> bool:
    if len(text) < MIN_TEXT_LENGTH:
        return False
    georgian = len(re.findall(r'[\u10A0-\u10FF]', text))
    latin = len(re.findall(r'[a-zA-Z]', text))
    digits = len(re.findall(r'\d', text))
    meaningful = georgian + latin + digits
    return (meaningful / len(text)) > MIN_TEXT_QUALITY


def _extract_pdf_native(file_bytes: bytes) -> str:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        return "\n\n".join(doc[i].get_text() for i in range(len(doc)))
    except Exception as e:
        log.warning("native PDF extraction failed: %s", e)
        return ""


def _count_pdf_pages(file_bytes: bytes) -> int:
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        return len(doc)
    except Exception:
        return 0


def _ocr_pdf(file_bytes: bytes) -> str:
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
        images = convert_from_bytes(file_bytes, dpi=200)
        return "\n\n".join(
            pytesseract.image_to_string(img, lang="kat+eng+rus")
            for img in images
        )
    except Exception as e:
        log.warning("OCR PDF failed: %s", e)
        return ""


def _ocr_image(file_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(file_bytes))
        return pytesseract.image_to_string(img, lang="kat+eng+rus")
    except Exception as e:
        log.warning("OCR image failed: %s", e)
        return ""


async def _vision_extract(file_bytes: bytes, mime_type: str, llm_service) -> str:
    try:
        import base64
        if mime_type == "application/pdf":
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(file_bytes, dpi=150)
            b64_list = []
            for img in images[:5]:
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                b64_list.append(base64.b64encode(buf.getvalue()).decode())
            return await llm_service.vision_ocr(images_base64=b64_list, media_type="image/png")
        else:
            b64 = base64.b64encode(file_bytes).decode()
            return await llm_service.vision_ocr(images_base64=[b64], media_type=mime_type)
    except Exception as e:
        log.warning("Vision LLM extraction failed: %s", e)
        return ""


async def parse_document(file_bytes: bytes, mime_type: str, llm_service=None) -> dict:
    """Extract text from PDF or image. Returns {text, method, pages_count}."""
    if mime_type == "application/pdf":
        text = _extract_pdf_native(file_bytes)
        if _is_good_text(text):
            return {"text": text, "method": "native_pdf", "pages_count": _count_pdf_pages(file_bytes)}

        log.info("Native PDF weak, trying OCR")
        text = _ocr_pdf(file_bytes)
        if _is_good_text(text):
            return {"text": text, "method": "tesseract_pdf", "pages_count": 0}

        if llm_service:
            log.info("OCR weak, trying vision LLM")
            text = await _vision_extract(file_bytes, mime_type, llm_service)
            return {"text": text, "method": "vision_llm", "pages_count": 0}

        return {"text": text, "method": "tesseract_pdf_low_quality", "pages_count": 0}

    elif mime_type.startswith("image/"):
        text = _ocr_image(file_bytes)
        if _is_good_text(text):
            return {"text": text, "method": "tesseract_image", "pages_count": 1}

        if llm_service:
            text = await _vision_extract(file_bytes, mime_type, llm_service)
            return {"text": text, "method": "vision_llm", "pages_count": 1}

        return {"text": text, "method": "tesseract_image_low_quality", "pages_count": 1}

    return {"text": "", "method": "unsupported", "pages_count": 0}
