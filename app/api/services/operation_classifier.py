"""app/api/services/operation_classifier.py
Keyword-based operation category classifier with LLM fallback.
"""
from __future__ import annotations
import logging
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)


class OperationCategory(str, Enum):
    MARKETING_SEO = "marketing_seo"
    MARKETING_ADS = "marketing_ads"
    OFFICE_SUPPLIES = "office_supplies"
    OFFICE_RENT = "office_rent"
    UTILITIES = "utilities"
    IT_SERVICES = "it_services"
    IT_SAAS = "it_saas"
    IT_HARDWARE = "it_hardware"
    CONSULTING = "consulting"
    LEGAL = "legal"
    ACCOUNTING = "accounting"
    EDUCATION = "education"
    TRANSPORT = "transport"
    FOOD_BEVERAGE = "food_beverage"
    BANK_FEES = "bank_fees"
    ADVANCE_PAYMENT = "advance_payment"
    CONTRACT = "contract"
    SALARY = "salary"
    FURNITURE = "furniture"
    OTHER = "other"


CATEGORY_KEYWORDS: dict[OperationCategory, list[str]] = {
    OperationCategory.MARKETING_SEO: ["seo", "ოპტიმიზაცია", "search engine"],
    OperationCategory.MARKETING_ADS: [
        "რეკლამა", "marketing", "მარკეტინგი", "facebook ads",
        "google ads", "სოციალური", "promoted",
    ],
    OperationCategory.OFFICE_SUPPLIES: [
        "საკანცელარიო", "ქაღალდი", "კალამი", "სტამბა",
        "ბეჭდვა", "ფარდა", "სკამი", "მაგიდა", "საოფისე",
        "სეიფი", "ფოტო", "კარტრიჯი",
    ],
    OperationCategory.OFFICE_RENT: ["ქირა", "იჯარა", "ოფისის ყოველთვიური", "rent"],
    OperationCategory.UTILITIES: [
        "ელექტრო", "წყალი", "გაზი", "ინტერნეტი", "ტელეფონი",
        "კომუნალ", "სილქნეტი", "magti", "silknet", "geocell",
    ],
    OperationCategory.IT_SERVICES: [
        "სისტემის განახლება", "პროგრამირება", "ვებ-გვერდი",
        "development", "implementation", "ინტეგრაცია",
    ],
    OperationCategory.IT_SAAS: [
        "სისტემაზე წვდომა", "subscription", "აბონამენტი", "cloud",
        "google workspace", "microsoft 365", "aws", "ლიცენზია",
    ],
    OperationCategory.IT_HARDWARE: [
        "კომპიუტერი", "ლეპტოპი", "მონიტორი", "პრინტერი",
        "laptop", "monitor", "ssd", "usb", "sandisk",
    ],
    OperationCategory.CONSULTING: ["კონსულტაცია", "consulting", "რჩევა"],
    OperationCategory.LEGAL: ["იურიდიული", "სამართალი", "legal"],
    OperationCategory.ACCOUNTING: ["საბუღალტრო", "აუდიტი", "accounting"],
    OperationCategory.EDUCATION: [
        "სწავლება", "ტრენინგი", "კურსი", "კვლევა",
        "journal", "ელექტრონული რესურსი", "e-book", "acm", "sage", "elsevier",
    ],
    OperationCategory.TRANSPORT: ["ტრანსპორტი", "ტაქსი", "მიწოდება", "bolt", "uber"],
    OperationCategory.FOOD_BEVERAGE: [
        "კვება", "სასადილო", "კაფეთი", "ბუფეთი", "ღვინო", "vintages",
    ],
    OperationCategory.BANK_FEES: [
        "საბანკო საკომისიო", "bank fee", "commission", "საკომისიო",
    ],
    OperationCategory.ADVANCE_PAYMENT: [
        "ავანსი", "წინასწარი გადახდა", "advance", "prepayment",
    ],
    OperationCategory.CONTRACT: [
        "ხელშეკრულება", "სახელმძღვანელო", "agreement", "memorandum",
    ],
    OperationCategory.SALARY: ["ხელფასი", "salary", "payroll"],
    OperationCategory.FURNITURE: ["ავეჯი", "სავარძელ", "მაგიდა", "კარადა"],
}

CATEGORY_TO_ACCOUNT: dict[OperationCategory, str] = {
    OperationCategory.MARKETING_SEO: "7420",
    OperationCategory.MARKETING_ADS: "7420",
    OperationCategory.OFFICE_SUPPLIES: "7440",
    OperationCategory.OFFICE_RENT: "7460",
    OperationCategory.UTILITIES: "7430",
    OperationCategory.IT_SERVICES: "7410",
    OperationCategory.IT_SAAS: "7470",
    OperationCategory.IT_HARDWARE: "2110",
    OperationCategory.CONSULTING: "7410",
    OperationCategory.LEGAL: "7411",
    OperationCategory.ACCOUNTING: "7412",
    OperationCategory.EDUCATION: "7480",
    OperationCategory.TRANSPORT: "7450",
    OperationCategory.FOOD_BEVERAGE: "7490",
    OperationCategory.BANK_FEES: "7510",
    OperationCategory.ADVANCE_PAYMENT: "1490",
    OperationCategory.CONTRACT: "7410",
    OperationCategory.SALARY: "5010",
    OperationCategory.FURNITURE: "2120",
    OperationCategory.OTHER: "7490",
}


def classify_operation(doc, llm_service=None) -> tuple[OperationCategory, float]:
    """Classify operation category from extracted document. Returns (category, confidence)."""
    text_parts = [item.description for item in (doc.line_items or [])]
    if doc.notes:
        text_parts.append(doc.notes)
    text = " ".join(text_parts).lower()

    scores: dict[OperationCategory, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        matches = sum(1 for kw in keywords if kw.lower() in text)
        if matches > 0:
            scores[category] = matches

    if scores:
        best_cat, best_score = max(scores.items(), key=lambda x: x[1])
        if best_score >= 2:
            return best_cat, 0.95
        elif best_score == 1:
            return best_cat, 0.75

    return OperationCategory.OTHER, 0.30


async def classify_operation_async(doc, llm_service=None) -> tuple[OperationCategory, float]:
    """Async version — tries keyword first, then LLM fallback."""
    category, confidence = classify_operation(doc)
    if confidence >= 0.75 or llm_service is None:
        return category, confidence

    try:
        categories = [c.value for c in OperationCategory]
        descriptions = "\n".join(f"- {item.description}" for item in (doc.line_items or []))
        prompt = (
            f"Document line items:\n{descriptions}\n\n"
            f"Categories: {', '.join(categories)}\n\n"
            "Return ONLY the category name, nothing else."
        )
        response = await llm_service.complete(prompt=prompt, max_tokens=30, temperature=0.1)
        cat_str = response.strip().lower().replace(" ", "_")
        for cat in OperationCategory:
            if cat.value == cat_str:
                return cat, 0.85
    except Exception as e:
        log.warning("LLM classify failed: %s", e)

    return OperationCategory.OTHER, 0.50
