"""app/api/services/party_resolver.py
Determines whether our tenant is BUYER, SELLER, INTERNAL, or FOREIGN
relative to a parsed document.
"""
import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.api.services.document_extractor import ExtractedDocument, ExtractedParty
from app.api.db import get_conn, _q

log = logging.getLogger(__name__)


class OurRole(str, Enum):
    BUYER = "buyer"
    SELLER = "seller"
    INTERNAL = "internal"
    FOREIGN = "foreign"
    UNKNOWN = "unknown"


@dataclass
class PartyResolution:
    our_role: OurRole
    counterparty_inn: Optional[str]
    counterparty_name: Optional[str]
    our_tenant_name: str
    our_tenant_inn: str
    confidence: float
    warnings: list = field(default_factory=list)


async def _load_tenant(tenant_id: str) -> dict:
    _TENANT_COLS = "company_inn, company_name_legal, company_name_aliases, owner_personal_id, company_type, is_vat_payer"
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(
                _q(f"SELECT {_TENANT_COLS} FROM tenants WHERE tenant_id = %s"), tenant_id
            )
            if not row:
                row = await conn.fetchrow(
                    _q(f"SELECT {_TENANT_COLS} FROM tenants WHERE company_inn = %s"), tenant_id
                )
        if not row:
            return {"inn": "", "name": tenant_id, "aliases": [], "owner_personal_id": None,
                    "company_type": "legal_entity", "is_vat_payer": True}
        return {
            "inn": row["company_inn"] or "",
            "name": row["company_name_legal"] or tenant_id,
            "aliases": row["company_name_aliases"] or [],
            "owner_personal_id": row["owner_personal_id"],
            "company_type": row["company_type"] or "legal_entity",
            "is_vat_payer": bool(row["is_vat_payer"]),
        }
    except Exception as e:
        log.warning("_load_tenant failed: %s", e)
        return {"inn": "", "name": tenant_id, "aliases": [], "owner_personal_id": None,
                "company_type": "legal_entity", "is_vat_payer": True}


def _normalize_name(name: str) -> str:
    if not name:
        return ""
    n = name.lower().strip()
    for prefix in ["შპს ", "სს ", "ა/ა ", "ფასდ ", "llc ", "jsc ", "ltd "]:
        if n.startswith(prefix):
            n = n[len(prefix):]
            break
    return re.sub(r'\s+', ' ', n)


def _is_us(party: ExtractedParty, tenant: dict) -> bool:
    our_inn = tenant["inn"]
    if party.inn and our_inn and party.inn.strip() == our_inn:
        return True

    owner_id = tenant.get("owner_personal_id")
    if party.inn and owner_id and party.inn.strip() == owner_id:
        return True

    if party.name:
        party_norm = _normalize_name(party.name)
        if _normalize_name(tenant["name"]) == party_norm:
            return True
        aliases = tenant.get("aliases") or []
        if isinstance(aliases, str):
            import json
            try:
                aliases = json.loads(aliases)
            except Exception:
                aliases = []
        for alias in aliases:
            alias_norm = _normalize_name(str(alias))
            if alias_norm and (alias_norm in party_norm or party_norm in alias_norm):
                return True

    return False


async def resolve_party(doc: ExtractedDocument, tenant_id: str) -> PartyResolution:
    tenant = await _load_tenant(tenant_id)
    warnings = []

    seller_is_us = _is_us(doc.seller, tenant)
    buyer_is_us = _is_us(doc.buyer, tenant)

    if buyer_is_us and not seller_is_us:
        role = OurRole.BUYER
        cp_inn = doc.seller.inn
        cp_name = doc.seller.name
        confidence = 0.95 if doc.seller.inn else 0.75

    elif seller_is_us and not buyer_is_us:
        role = OurRole.SELLER
        cp_inn = doc.buyer.inn
        cp_name = doc.buyer.name
        confidence = 0.95 if doc.buyer.inn else 0.75

    elif seller_is_us and buyer_is_us:
        role = OurRole.INTERNAL
        cp_inn = None
        cp_name = None
        confidence = 0.90
        warnings.append("ორივე მხარე ჩვენია (internal transfer)")

    else:
        role = OurRole.FOREIGN
        cp_inn = None
        cp_name = None
        # Graduated confidence: higher when both INNs extracted (document was readable)
        if doc.seller.inn and doc.buyer.inn:
            confidence = 0.50   # both INNs extracted — system understood doc, just not our tenant
        elif doc.seller.inn or doc.buyer.inn:
            confidence = 0.35   # one INN extracted
        else:
            confidence = 0.10   # no INNs — likely unreadable or wrong doc
        owner_id = tenant.get("owner_personal_id")
        if owner_id and (doc.buyer.inn == owner_id or doc.seller.inn == owner_id):
            warnings.append(
                f"დოკუმენტი შეიცავს მფლობელის პირად ID-ს ({owner_id}), "
                f"მაგრამ გამოყენებულ კომპანიას ({tenant['name']}) არ ეკუთვნის. "
                "შესაძლოა პირადი ხარჯი."
            )
        else:
            seller_info = f"{doc.seller.name or '?'} (ID: {doc.seller.inn or '?'})"
            buyer_info = f"{doc.buyer.name or '?'} (ID: {doc.buyer.inn or '?'})"
            warnings.append(
                f"დოკუმენტი არ ეკუთვნის {tenant['name']}-ს. "
                f"გამყიდველი: {seller_info}. მყიდველი: {buyer_info}."
            )

    return PartyResolution(
        our_role=role,
        counterparty_inn=cp_inn,
        counterparty_name=cp_name,
        our_tenant_name=tenant["name"],
        our_tenant_inn=tenant["inn"],
        confidence=confidence,
        warnings=warnings,
    )
