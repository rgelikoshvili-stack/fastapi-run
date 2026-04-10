import os
from typing import Dict, Any

from app.api.services.ocr_service import extract_text
from bridge_hub_knowledge import build_journal_from_text


def detect_document_type(text: str) -> str:
    t = (text or "").lower()

    if "invoice" in t or "ინვოისი" in t:
        return "invoice"
    if "contract" in t or "ხელშეკრულება" in t:
        return "contract"
    if "statement" in t or "ამონაწერი" in t:
        return "statement"

    return "unknown"


def process_document(file_path: str) -> Dict[str, Any]:
    text = extract_text(file_path)

    if not text:
        return {
            "ok": False,
            "message": "❌ ფაილიდან ტექსტი ვერ ამოვიკითხე",
            "description": "Unreadable document",
            "lines": [],
            "document_type": "unknown",
        }

    document_type = detect_document_type(text)
    posting = build_journal_from_text(text)

    return {
        "ok": True,
        "message": posting.get("message", "დოკუმენტი დამუშავდა"),
        "description": posting.get("description", f"{document_type.title()} Posting"),
        "lines": posting.get("lines", []),
        "document_type": document_type,
        "raw_text_preview": text[:1000],
        "filename": os.path.basename(file_path),
    }