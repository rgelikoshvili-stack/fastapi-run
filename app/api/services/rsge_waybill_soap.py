"""app/api/services/rsge_waybill_soap.py

RS.ge WayBill SOAP client.

Endpoint: https://services.rs.ge/WayBillService/WayBillService.asmx
Auth: su (service username) + sp (service password)
      Created per-tenant in the RS.ge portal under: Settings → Service Users

Protocol reference: waybill_protocol.pdf v4.0.4 (2024-10)
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

import httpx

log = logging.getLogger(__name__)

WAYBILL_SOAP_URL = "https://services.rs.ge/WayBillService/WayBillService.asmx"
_NS = "http://services.rs.ge/"
_TIMEOUT = 30.0

# Waybill statuses
STATUS_SAVED = 0
STATUS_ACTIVE = 1
STATUS_CLOSED = 2
STATUS_SENT_TO_CARRIER = 8
STATUS_DELETED = -1
STATUS_CANCELLED = -2

STATUS_LABEL = {
    0: "შენახული",
    1: "აქტიური",
    2: "დასრულებული",
    8: "გადამზიდავთან",
    -1: "წაშლილი",
    -2: "გაუქმებული",
}


def _soap_envelope(method: str, params: dict) -> str:
    """Build a SOAP 1.1 envelope for a WayBillService method call."""
    param_xml = ""
    for key, val in params.items():
        if val is None:
            param_xml += f"<{key}/>"
        else:
            escaped = str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            param_xml += f"<{key}>{escaped}</{key}>"

    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
        f'<{method} xmlns="{_NS}">'
        f"{param_xml}"
        f"</{method}>"
        "</soap:Body>"
        "</soap:Envelope>"
    )


def _call(method: str, params: dict) -> ET.Element:
    """Execute a SOAP call; return the inner result Element."""
    body = _soap_envelope(method, params)
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f'"{_NS}{method}"',
    }
    with httpx.Client(timeout=_TIMEOUT, verify=True) as client:
        resp = client.post(WAYBILL_SOAP_URL, content=body.encode("utf-8"), headers=headers)
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    # Strip SOAP envelope: Body > {method}Response > {method}Result
    ns_soap = "http://schemas.xmlsoap.org/soap/envelope/"
    body_el = root.find(f"{{{ns_soap}}}Body")
    if body_el is None:
        raise ValueError("SOAP response has no Body")

    # Walk into the first child (the Response element) and find the result
    for child in body_el:
        # Try {method}Result first
        result = child.find(f"{{{_NS}}}{method}Result")
        if result is not None:
            return result
        # Some .asmx return the content directly
        return child

    raise ValueError(f"Empty SOAP body for {method}")


def _text(el: Optional[ET.Element], tag: str, default: str = "") -> str:
    if el is None:
        return default
    child = el.find(tag)
    if child is None or child.text is None:
        return default
    return child.text.strip()


def _int(el: Optional[ET.Element], tag: str, default: Optional[int] = None) -> Optional[int]:
    v = _text(el, tag)
    if not v:
        return default
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


def _float(el: Optional[ET.Element], tag: str, default: float = 0.0) -> float:
    v = _text(el, tag)
    if not v:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _parse_waybill_list(result: ET.Element) -> list[dict]:
    """Parse a <WAYBILL_LIST> element into a list of waybill dicts."""
    waybills = []
    # result may BE the WAYBILL_LIST or contain it
    wb_list = result if result.tag.endswith("WAYBILL_LIST") else result.find("WAYBILL_LIST")
    if wb_list is None:
        # Try direct WAYBILL children
        wb_list = result
    for wb in wb_list.findall("WAYBILL"):
        goods = []
        gl = wb.find("GOODS_LIST")
        if gl is not None:
            for g in gl.findall("GOODS"):
                goods.append({
                    "id": _int(g, "ID"),
                    "name": _text(g, "W_NAME"),
                    "unit_id": _int(g, "UNIT_ID"),
                    "unit_txt": _text(g, "UNIT_TXT"),
                    "quantity": _float(g, "QUANTITY"),
                    "price": _float(g, "PRICE"),
                    "amount": _float(g, "AMOUNT"),
                    "bar_code": _text(g, "BAR_CODE"),
                    "vat_type": _int(g, "VAT_TYPE", 0),
                })
        waybills.append({
            "rsge_id": _text(wb, "ID"),
            "waybill_number": _text(wb, "WAYBILL_NUMBER"),
            "type": _int(wb, "TYPE"),
            "status_code": _int(wb, "STATUS", 0),
            "status": STATUS_LABEL.get(_int(wb, "STATUS", 0), ""),
            "create_date": _text(wb, "CREATE_DATE"),
            "begin_date": _text(wb, "BEGIN_DATE"),
            "activate_date": _text(wb, "ACTIVATE_DATE"),
            "close_date": _text(wb, "CLOSE_DATE"),
            "delivery_date": _text(wb, "DELIVERY_DATE"),
            "seller_tin": _text(wb, "SELLER_TIN"),
            "seller_name": _text(wb, "SELLER_NAME"),
            "buyer_tin": _text(wb, "BUYER_TIN"),
            "buyer_name": _text(wb, "BUYER_NAME"),
            "driver_tin": _text(wb, "DRIVER_TIN"),
            "driver_name": _text(wb, "DRIVER_NAME"),
            "car_number": _text(wb, "CAR_NUMBER"),
            "start_address": _text(wb, "START_ADDRESS"),
            "end_address": _text(wb, "END_ADDRESS"),
            "full_amount": _float(wb, "FULL_AMOUNT"),
            "comment": _text(wb, "WAYBILL_COMMENT") or _text(wb, "COMMENT"),
            "goods_list": goods,
        })
    return waybills


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def get_waybills_v1(
    su: str,
    sp: str,
    last_update_date_s: datetime,
    last_update_date_e: datetime,
    buyer_tin: Optional[str] = None,
) -> list[dict]:
    """Return waybills (both sold and bought) updated in the given time window.

    Max window: 3 days per call (RS.ge constraint).
    Result includes records where the authenticated user is either buyer OR seller.
    """
    result = _call("get_waybills_v1", {
        "su": su,
        "sp": sp,
        "buyer_tin": buyer_tin or "",
        "last_update_date_s": fmt_dt(last_update_date_s),
        "last_update_date_e": fmt_dt(last_update_date_e),
    })
    return _parse_waybill_list(result)


def get_waybills(
    su: str,
    sp: str,
    create_date_s: Optional[datetime] = None,
    create_date_e: Optional[datetime] = None,
    statuses: str = "",
    buyer_tin: str = "",
    waybill_number: str = "",
) -> list[dict]:
    """Return seller-side waybills with optional filters."""
    result = _call("get_waybills", {
        "su": su,
        "sp": sp,
        "itypes": "",
        "buyer_tin": buyer_tin,
        "statuses": statuses,
        "car_number": "",
        "begin_date_s": fmt_dt(create_date_s) if create_date_s else "",
        "begin_date_e": fmt_dt(create_date_e) if create_date_e else "",
        "create_date_s": fmt_dt(create_date_s) if create_date_s else "",
        "create_date_e": fmt_dt(create_date_e) if create_date_e else "",
        "driver_tin": "",
        "delivery_date_s": "",
        "delivery_date_e": "",
        "full_amount": "",
        "waybill_number": waybill_number,
        "close_date_s": "",
        "close_date_e": "",
        "s_user_ids": "",
        "comment": "",
    })
    return _parse_waybill_list(result)


def get_buyer_waybills(
    su: str,
    sp: str,
    create_date_s: Optional[datetime] = None,
    create_date_e: Optional[datetime] = None,
    statuses: str = "",
    seller_tin: str = "",
) -> list[dict]:
    """Return buyer-side waybills (where the authenticated user is the buyer)."""
    result = _call("get_buyer_waybills", {
        "su": su,
        "sp": sp,
        "itypes": "",
        "seller_tin": seller_tin,
        "statuses": statuses,
        "car_number": "",
        "begin_date_s": fmt_dt(create_date_s) if create_date_s else "",
        "begin_date_e": fmt_dt(create_date_e) if create_date_e else "",
        "create_date_s": fmt_dt(create_date_s) if create_date_s else "",
        "create_date_e": fmt_dt(create_date_e) if create_date_e else "",
        "driver_tin": "",
        "delivery_date_s": "",
        "delivery_date_e": "",
        "full_amount": "",
        "waybill_number": "",
        "close_date_s": "",
        "close_date_e": "",
        "s_user_ids": "",
        "comment": "",
    })
    return _parse_waybill_list(result)


def get_single_waybill(su: str, sp: str, waybill_id: int) -> Optional[dict]:
    """Fetch a single waybill by its internal ID."""
    result = _call("get_waybill", {"su": su, "sp": sp, "waybill_id": waybill_id})
    # get_waybill returns a single <WAYBILL> element
    wb = result if result.tag.endswith("WAYBILL") else result.find("WAYBILL")
    if wb is None:
        return None

    goods = []
    gl = wb.find("GOODS_LIST")
    if gl is not None:
        for g in gl.findall("GOODS"):
            goods.append({
                "id": _int(g, "ID"),
                "name": _text(g, "W_NAME"),
                "unit_id": _int(g, "UNIT_ID"),
                "unit_txt": _text(g, "UNIT_TXT"),
                "quantity": _float(g, "QUANTITY"),
                "price": _float(g, "PRICE"),
                "amount": _float(g, "AMOUNT"),
                "bar_code": _text(g, "BAR_CODE"),
                "vat_type": _int(g, "VAT_TYPE", 0),
            })

    return {
        "rsge_id": _text(wb, "ID"),
        "waybill_number": _text(wb, "WAYBILL_NUMBER"),
        "type": _int(wb, "TYPE"),
        "status_code": _int(wb, "STATUS", 0),
        "status": STATUS_LABEL.get(_int(wb, "STATUS", 0), ""),
        "create_date": _text(wb, "CREATE_DATE"),
        "begin_date": _text(wb, "BEGIN_DATE"),
        "activate_date": _text(wb, "ACTIVATE_DATE"),
        "close_date": _text(wb, "CLOSE_DATE"),
        "seller_un_id": _text(wb, "SELER_UN_ID"),
        "buyer_tin": _text(wb, "BUYER_TIN"),
        "buyer_name": _text(wb, "BUYER_NAME"),
        "driver_tin": _text(wb, "DRIVER_TIN"),
        "driver_name": _text(wb, "DRIVER_NAME"),
        "car_number": _text(wb, "CAR_NUMBER"),
        "start_address": _text(wb, "START_ADDRESS"),
        "end_address": _text(wb, "END_ADDRESS"),
        "full_amount": _float(wb, "FULL_AMOUNT"),
        "comment": _text(wb, "COMMENT"),
        "goods_list": goods,
    }
