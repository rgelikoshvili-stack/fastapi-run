"""app/api/services/contract_classifier.py
Provider / counterparty type detection for Georgian business documents.

Provider types:
  fp  — ფიზიკური პირი (individual, INN = 11 digits)
  im  — ინდივიდუალური მეწარმე (sole trader, INN = 9 digits but registered as entrepreneur)
  shps — შეზღუდული პასუხისმგებლობის საზოგადოება (LLC)
  sp   — სააქციო საზოგადოება (JSC)
  npo  — non-profit / NGO / foundation
  unknown
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class ProviderType(str, Enum):
    FP    = "fp"       # ფიზიკური პირი
    IM    = "im"       # ინდივიდუალური მეწარმე
    SHPS  = "shps"     # შპს
    SP    = "sp"       # სს
    NPO   = "npo"      # ფონდი / ასოციაცია
    UNKNOWN = "unknown"


_SHPS_PATTERNS = [
    r"\bშპს\b", r"\bshps\b", r"\bООО\b",
    r"შეზღუდული\s+პასუხისმგებლობის",
]
_SP_PATTERNS = [
    r"\bსს\b", r"\bss\b", r"სააქციო\s+საზოგადოება",
    r"\bАО\b", r"\bJSC\b",
]
_IM_PATTERNS = [
    r"\bი\s*\.\s*მ\b", r"\bი\.მ\.", r"\bIM\b",
    r"ინდივიდუალური\s+მეწარმე", r"individual\s+entrepreneur",
]
_FP_PATTERNS = [
    r"\bფ\s*\.\s*პ\b", r"\bფ\.პ\.", r"\bFP\b",
    r"ფიზიკური\s+პირი", r"physical\s+person",
]
_NPO_PATTERNS = [
    r"\bფონდი\b", r"\bასოციაცია\b", r"\bNGO\b",
    r"\bNPO\b", r"non[-\s]?profit",
]

_INN_RE = re.compile(r'\b(\d{9}|\d{11})\b')


def classify_provider_type(
    name: Optional[str],
    inn: Optional[str] = None,
    doc_text: Optional[str] = None,
) -> ProviderType:
    """
    Detect provider type from company name, INN length, or document text.

    Priority: explicit keyword > INN length heuristic
    """
    search_corpus = " ".join(filter(None, [name or "", doc_text or ""]))
    corpus_lower = search_corpus.lower()

    for pat in _SHPS_PATTERNS:
        if re.search(pat, search_corpus, re.IGNORECASE):
            return ProviderType.SHPS

    for pat in _SP_PATTERNS:
        if re.search(pat, search_corpus, re.IGNORECASE):
            return ProviderType.SP

    for pat in _NPO_PATTERNS:
        if re.search(pat, search_corpus, re.IGNORECASE):
            return ProviderType.NPO

    for pat in _IM_PATTERNS:
        if re.search(pat, search_corpus, re.IGNORECASE):
            return ProviderType.IM

    for pat in _FP_PATTERNS:
        if re.search(pat, search_corpus, re.IGNORECASE):
            return ProviderType.FP

    # INN length heuristic (fallback)
    if inn:
        inn_clean = re.sub(r'\D', '', inn)
        if len(inn_clean) == 11:
            return ProviderType.FP
        if len(inn_clean) == 9:
            # Could be IM or SHPS — prefer IM if name looks personal
            return ProviderType.SHPS  # most common 9-digit entity

    return ProviderType.UNKNOWN


def needs_pit_withholding(provider_type: ProviderType) -> bool:
    """True when we must withhold PIT (20%) + PAYG (2%) + pension (2%)."""
    return provider_type in (ProviderType.FP, ProviderType.IM)


def needs_vat_reverse_charge(provider_type: ProviderType) -> bool:
    """True for foreign service providers (not applicable here — placeholder)."""
    return False


def classify_from_extracted_doc(doc) -> dict:
    """
    Given an ExtractedDocument (or dict), classify both seller and buyer,
    returning a dict with provider_type, needs_pit, our_role hint.
    """
    seller = getattr(doc, "seller", None) or {}
    buyer  = getattr(doc, "buyer", None) or {}

    if hasattr(seller, "inn"):
        seller_inn  = seller.inn
        seller_name = seller.name
    else:
        seller_inn  = seller.get("inn")
        seller_name = seller.get("name")

    if hasattr(buyer, "inn"):
        buyer_inn  = buyer.inn
        buyer_name = buyer.name
    else:
        buyer_inn  = buyer.get("inn")
        buyer_name = buyer.get("name")

    seller_type = classify_provider_type(seller_name, seller_inn)
    buyer_type  = classify_provider_type(buyer_name, buyer_inn)

    return {
        "seller_type":  seller_type,
        "buyer_type":   buyer_type,
        "seller_needs_pit": needs_pit_withholding(seller_type),
        "buyer_needs_pit":  needs_pit_withholding(buyer_type),
    }
