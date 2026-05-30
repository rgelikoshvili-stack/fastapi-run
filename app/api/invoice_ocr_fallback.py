def extract_text_with_ocr(file_bytes: bytes) -> str:
    try:
        import pytesseract
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(file_bytes)

        full_text = ""

        for img in images:
            text = pytesseract.image_to_string(img, lang="eng")
            full_text += text + "\n"

        return full_text.strip()

    except Exception as e:
        import logging; logging.getLogger(__name__).warning("ocr fallback failed: %s", e)
        return ""