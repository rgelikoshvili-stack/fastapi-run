"""
decision_engine/normalize.py
Text normalization, VAT parsing, partner normalization.
"""
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

_GEO_STOPWORDS = frozenset([
    "შპს", "სს", "ინდ", "მეწარმე", "სახელმწიფო", "კომპანია",
    "ჯგუფი", "ფილიალი", "საქართველო", "tbilisi", "თბილისი",
])
_EN_STOPWORDS = frozenset([
    "llc", "ltd", "inc", "corp", "co", "group", "georgia",
    "tbilisi", "company", "the", "and", "for", "payment",
    "invoice", "bill", "transfer", "to", "from", "via",
])

_GEO_UNICODE = r"\u10A0-\u10FF"
_PUNCT_PATTERN = re.compile(rf"[^\w\s{_GEO_UNICODE}]", re.UNICODE)
_SPACE_PATTERN = re.compile(r"\s+")

# Georgian VAT rate
VAT_RATE = Decimal("0.18")


def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    t = text.strip().lower()
    t = t.replace("\u201c", '"').replace("\u201d", '"')
    t = t.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    t = _PUNCT_PATTERN.sub(" ", t)
    t = _SPACE_PATTERN.sub(" ", t).strip()

    tokens = [w for w in t.split() if w not in _GEO_STOPWORDS and w not in _EN_STOPWORDS]
    return " ".join(tokens)


def parse_amount(
    value,
    vat_inclusive: Optional[bool] = None,
) -> dict:
    """
    Parse a monetary value and optionally split VAT.
    Returns: {gross, net, vat, vat_included}
    vat_inclusive=None → no VAT split attempted.
    """
    try:
        gross = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        gross = Decimal("0.00")

    if vat_inclusive is True:
        net = (gross / (1 + VAT_RATE)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        vat = (gross - net).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {"gross": float(gross), "net": float(net), "vat": float(vat), "vat_included": True}

    if vat_inclusive is False:
        vat = (gross * VAT_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {"gross": float(gross + vat), "net": float(gross), "vat": float(vat), "vat_included": False}

    return {"gross": float(gross), "net": float(gross), "vat": 0.0, "vat_included": None}


def detect_vat_flag(text: Optional[str]) -> Optional[bool]:
    """Return True=inclusive, False=exclusive, None=unknown."""
    if not text:
        return None
    tl = text.lower()
    if any(kw in tl for kw in ("დღგ ჩათვლით", "vat incl", "with vat", "vat included", "inclusive")):
        return True
    if any(kw in tl for kw in ("დღგ გარეშე", "vat excl", "without vat", "excl. vat", "exclusive")):
        return False
    return None


def normalize_partner(name: Optional[str]) -> str:
    if not name:
        return ""
    t = name.strip().lower()
    t = re.sub(r"[\"'«»()[\]{}]", " ", t)
    t = _SPACE_PATTERN.sub(" ", t).strip()

    tokens = [w for w in t.split()
              if w not in _GEO_STOPWORDS and w not in _EN_STOPWORDS and len(w) > 1]
    return " ".join(tokens)


def partner_similarity(a: Optional[str], b: Optional[str]) -> float:
    """Return WRatio similarity (0-100) between two partner names."""
    if not a or not b:
        return 0.0
    try:
        from rapidfuzz import fuzz
        return fuzz.WRatio(normalize_partner(a), normalize_partner(b))
    except ImportError:
        na, nb = normalize_partner(a), normalize_partner(b)
        if na == nb:
            return 100.0
        if na in nb or nb in na:
            return 80.0
        return 0.0
