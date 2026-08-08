"""app/api/connectors/rs_ge_connector.py — RS.ge (Revenue Service of Georgia) connector.

Implements two SOAP web services:
  WayBill  : https://services.rs.ge/WayBillService/WayBillService.asmx
  Invoice  : https://www.revenue.mof.ge/ntosservice/ntosservice.asmx

Plus REST:
  TaxPayer : https://xdata.rs.ge/TaxPayer/RSPublicInfo

Environment variables:
  RS_GE_SU   — service username (სერვისის მომხმარებელი)
  RS_GE_SP   — service password (სერვისის პაროლი)
  RS_GE_UN_ID — seller UN_ID returned by chek_service_user

Demo mode activates when RS_GE_SU is not set.
"""
import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

import requests

from app.api.connectors.base_connector import BaseConnector

log = logging.getLogger(__name__)

_WAYBILL_WSDL  = "https://services.rs.ge/WayBillService/WayBillService.asmx"
_INVOICE_WSDL  = "https://www.revenue.mof.ge/ntosservice/ntosservice.asmx"
_TAXPAYER_REST = "https://xdata.rs.ge/TaxPayer/RSPublicInfo"
_SOAP_NS       = "http://schemas.xmlsoap.org/soap/envelope/"
_WB_NS         = "http://services.rs.ge/"
_INV_NS        = "http://tempuri.org/"

WAYBILL_TYPES = {1: "შიდა გადაზიდვა", 2: "მიწოდება ტრანსპორტირებით",
                 3: "მიწოდება ტრანსპ. გარეშე", 4: "დისტრიბუცია", 5: "უკან დაბრუნება"}

WAYBILL_STATUS = {0: "შენახული", 1: "აქტიური", 2: "დასრულებული", 6: "გაუქმებული"}


def _soap_call(endpoint: str, method: str, ns: str, params: dict,
               timeout: int = 30) -> ET.Element:
    """Send a SOAP request and return the parsed response body element."""
    body_inner = "".join(
        f"<{k}>{v}</{k}>" for k, v in params.items() if not k.startswith("_xml_")
    )
    for k, v in params.items():
        if k.startswith("_xml_"):
            body_inner += v

    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<soap:Envelope xmlns:soap="{_SOAP_NS}" '
        f'               xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'               xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
        '<soap:Body>'
        f'<{method} xmlns="{ns}">'
        f'{body_inner}'
        f'</{method}>'
        '</soap:Body>'
        '</soap:Envelope>'
    )
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction":   f'"{ns}{method}"',
    }
    r = requests.post(endpoint, data=envelope.encode("utf-8"),
                      headers=headers, timeout=timeout, verify=True)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    # Return first child of soap:Body
    body = root.find(f"{{{_SOAP_NS}}}Body")
    if body is None:
        raise ValueError("No soap:Body in response")
    children = list(body)
    if not children:
        raise ValueError("Empty soap:Body")
    return children[0]


def _xml_text(element: Optional[ET.Element], tag: str, default: str = "") -> str:
    if element is None:
        return default
    el = element.find(tag)
    return (el.text or default).strip() if el is not None else default


def _build_waybill_xml(wb: dict) -> str:
    """Build the <WAYBILL> XML node from a dict."""
    goods = ""
    for g in wb.get("goods_list", []):
        goods += (
            "<GOODS>"
            f"<ID>{g.get('id', 0)}</ID>"
            f"<W_NAME>{g.get('name', '')}</W_NAME>"
            f"<UNIT_ID>{g.get('unit_id', 1)}</UNIT_ID>"
            f"<UNIT_TXT>{g.get('unit_txt', '')}</UNIT_TXT>"
            f"<QUANTITY>{g.get('quantity', 0)}</QUANTITY>"
            f"<PRICE>{g.get('price', 0)}</PRICE>"
            f"<STATUS>1</STATUS>"
            f"<AMOUNT>{g.get('amount', 0)}</AMOUNT>"
            f"<BAR_CODE>{g.get('bar_code', '')}</BAR_CODE>"
            f"<A_ID>{g.get('akciz_id', 0)}</A_ID>"
            f"<VAT_TYPE>{g.get('vat_type', 1)}</VAT_TYPE>"
            f"<QUANTITY_EXT>{g.get('quantity_ext', 0)}</QUANTITY_EXT>"
            "</GOODS>"
        )
    begin = wb.get("begin_date") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    xml = (
        "<WAYBILL>"
        "<SUB_WAYBILLS></SUB_WAYBILLS>"
        f"<GOODS_LIST>{goods}</GOODS_LIST>"
        "<WOOD_DOCS_LIST></WOOD_DOCS_LIST>"
        f"<ID>{wb.get('id', 0)}</ID>"
        f"<TYPE>{wb.get('type', 2)}</TYPE>"
        f"<BUYER_TIN>{wb.get('buyer_tin', '')}</BUYER_TIN>"
        f"<CHEK_BUYER_TIN>{wb.get('check_buyer_tin', 1)}</CHEK_BUYER_TIN>"
        f"<BUYER_NAME>{wb.get('buyer_name', '')}</BUYER_NAME>"
        f"<START_ADDRESS>{wb.get('start_address', '')}</START_ADDRESS>"
        f"<END_ADDRESS>{wb.get('end_address', '')}</END_ADDRESS>"
        f"<DRIVER_TIN>{wb.get('driver_tin', '')}</DRIVER_TIN>"
        f"<CHEK_DRIVER_TIN>{wb.get('check_driver_tin', 1)}</CHEK_DRIVER_TIN>"
        f"<DRIVER_NAME>{wb.get('driver_name', '')}</DRIVER_NAME>"
        f"<TRANSPORT_COAST>{wb.get('transport_cost', 0)}</TRANSPORT_COAST>"
        f"<RECEPTION_INFO>{wb.get('reception_info', '')}</RECEPTION_INFO>"
        f"<RECEIVER_INFO>{wb.get('receiver_info', '')}</RECEIVER_INFO>"
        f"<DELIVERY_DATE></DELIVERY_DATE>"
        f"<STATUS>{wb.get('status', 1)}</STATUS>"
        f"<SELER_UN_ID>{wb.get('seller_un_id', '')}</SELER_UN_ID>"
        f"<PAR_ID>{wb.get('parent_id', '')}</PAR_ID>"
        f"<FULL_AMOUNT>{wb.get('full_amount', 0)}</FULL_AMOUNT>"
        f"<CAR_NUMBER>{wb.get('car_number', '')}</CAR_NUMBER>"
        f"<S_USER_ID>{wb.get('s_user_id', '')}</S_USER_ID>"
        f"<BEGIN_DATE>{begin}</BEGIN_DATE>"
        f"<TRAN_COST_PAYER>{wb.get('tran_cost_payer', 1)}</TRAN_COST_PAYER>"
        f"<TRANS_ID>{wb.get('trans_id', 1)}</TRANS_ID>"
        f"<TRANS_TXT></TRANS_TXT>"
        f"<COMMENT>{wb.get('comment', '')}</COMMENT>"
        f"<CATEGORY></CATEGORY>"
        f"<IS_MED></IS_MED>"
        "</WAYBILL>"
    )
    return xml


class RsGeConnector(BaseConnector):
    """RS.ge connector — WayBill + Invoice + TaxPayer verification."""

    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self.su = os.environ.get("RS_GE_SU", "").strip()
        self.sp = os.environ.get("RS_GE_SP", "").strip()
        self.un_id = os.environ.get("RS_GE_UN_ID", "").strip()
        self.mode = "live" if self.su and self.sp else "demo"

    # ── BaseConnector ────────────────────────────────────────────────────────

    def status(self) -> dict:
        if self.mode == "demo":
            return {"connected": True, "mode": "demo",
                    "message": "RS.ge demo — set RS_GE_SU / RS_GE_SP to go live",
                    "services": ["waybill", "invoice", "taxpayer"],
                    "tenant_id": self.tenant_id}
        try:
            result = self.check_service_user()
            ok = result.get("valid", False)
            return {"connected": ok, "mode": "live",
                    "un_id": result.get("un_id"),
                    "s_user_id": result.get("s_user_id"),
                    "message": "OK" if ok else result.get("error", "auth failed"),
                    "tenant_id": self.tenant_id}
        except Exception as exc:
            return {"connected": False, "mode": "live",
                    "message": str(exc)[:150], "tenant_id": self.tenant_id}

    def validate_config(self) -> bool:
        if self.mode == "demo":
            return True
        return self.status().get("connected", False)

    def preview(self, draft: dict) -> dict:
        """Validate waybill fields before submission."""
        errors, warnings = [], []
        goods = draft.get("goods_list", [])
        if not goods:
            errors.append("goods_list is empty")
        if not draft.get("buyer_tin"):
            errors.append("buyer_tin is required")
        if not draft.get("start_address"):
            errors.append("start_address is required")
        if not draft.get("end_address"):
            errors.append("end_address is required")
        for i, g in enumerate(goods):
            if not g.get("name"):
                errors.append(f"goods[{i}].name is required")
            if not g.get("quantity") or float(g.get("quantity", 0)) <= 0:
                errors.append(f"goods[{i}].quantity must be > 0")
            if not g.get("price") or float(g.get("price", 0)) <= 0:
                errors.append(f"goods[{i}].price must be > 0")
            if not g.get("bar_code"):
                warnings.append(f"goods[{i}].bar_code is empty")
        if draft.get("type") not in (None, *WAYBILL_TYPES.keys()):
            errors.append(f"type must be one of {list(WAYBILL_TYPES.keys())}")
        return {"valid": len(errors) == 0, "mode": self.mode,
                "errors": errors, "warnings": warnings}

    def post(self, draft: dict) -> dict:
        """Submit a waybill to RS.ge WayBill service."""
        if self.mode == "demo":
            wb_num = f"DEMO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            log.info("[RS.GE] DEMO waybill: %s", wb_num)
            return self._build_success(wb_num)
        try:
            if self.un_id:
                draft["seller_un_id"] = self.un_id
            xml_body = _build_waybill_xml(draft)
            resp = _soap_call(
                _WAYBILL_WSDL, "save_waybill", _WB_NS,
                {"su": self.su, "sp": self.sp, "_xml_waybill": xml_body}
            )
            status = _xml_text(resp, "STATUS")
            wb_id  = _xml_text(resp, "ID")
            if status == "0":
                log.info("[RS.GE] waybill saved id=%s", wb_id)
                return self._build_success(wb_id)
            return self._build_error(f"RS.ge error status={status}", status)
        except Exception as exc:
            log.warning("[RS.GE] save_waybill failed: %s", exc)
            return self._build_error(str(exc)[:200])

    def history(self, tenant_id: str, limit: int = 50) -> list:
        """Fetch recent waybills from RS.ge."""
        if self.mode == "demo":
            return []
        try:
            end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            start = "2024-01-01T00:00:00"
            resp = _soap_call(
                _WAYBILL_WSDL, "get_waybills_v1", _WB_NS,
                {"su": self.su, "sp": self.sp,
                 "last_update_date_s": start, "last_update_date_e": end}
            )
            items = []
            for wb in resp.iter("WAYBILL"):
                items.append({
                    "id":             _xml_text(wb, "ID"),
                    "waybill_number": _xml_text(wb, "WAYBILL_NUMBER"),
                    "type":           _xml_text(wb, "TYPE"),
                    "status":         _xml_text(wb, "STATUS"),
                    "buyer_name":     _xml_text(wb, "BUYER_NAME"),
                    "buyer_tin":      _xml_text(wb, "BUYER_TIN"),
                    "full_amount":    _xml_text(wb, "FULL_AMOUNT"),
                    "begin_date":     _xml_text(wb, "BEGIN_DATE"),
                })
                if len(items) >= limit:
                    break
            return items
        except Exception as exc:
            log.warning("[RS.GE] get_waybills_v1 failed: %s", exc)
            return []

    # ── WayBill extras ───────────────────────────────────────────────────────

    def get_waybill(self, waybill_id: int) -> dict:
        """Fetch a single waybill by ID."""
        if self.mode == "demo":
            return {"id": waybill_id, "mode": "demo",
                    "waybill_number": f"DEMO-{waybill_id:010d}", "status": "1"}
        try:
            resp = _soap_call(
                _WAYBILL_WSDL, "get_waybill", _WB_NS,
                {"su": self.su, "sp": self.sp, "waybill_id": waybill_id}
            )
            goods = []
            for g in resp.iter("GOODS"):
                goods.append({
                    "id":       _xml_text(g, "ID"),
                    "name":     _xml_text(g, "W_NAME"),
                    "quantity": _xml_text(g, "QUANTITY"),
                    "price":    _xml_text(g, "PRICE"),
                    "amount":   _xml_text(g, "AMOUNT"),
                    "unit_id":  _xml_text(g, "UNIT_ID"),
                    "bar_code": _xml_text(g, "BAR_CODE"),
                })
            return {
                "id":             _xml_text(resp, "ID"),
                "waybill_number": _xml_text(resp, "WAYBILL_NUMBER"),
                "type":           _xml_text(resp, "TYPE"),
                "status":         _xml_text(resp, "STATUS"),
                "buyer_name":     _xml_text(resp, "BUYER_NAME"),
                "buyer_tin":      _xml_text(resp, "BUYER_TIN"),
                "start_address":  _xml_text(resp, "START_ADDRESS"),
                "end_address":    _xml_text(resp, "END_ADDRESS"),
                "driver_name":    _xml_text(resp, "DRIVER_NAME"),
                "car_number":     _xml_text(resp, "CAR_NUMBER"),
                "full_amount":    _xml_text(resp, "FULL_AMOUNT"),
                "begin_date":     _xml_text(resp, "BEGIN_DATE"),
                "goods_list":     goods,
            }
        except Exception as exc:
            log.warning("[RS.GE] get_waybill failed: %s", exc)
            return {"error": str(exc)[:200]}

    def cancel_waybill(self, waybill_id: int) -> dict:
        """Cancel (deactivate) a waybill."""
        if self.mode == "demo":
            return {"success": True, "mode": "demo"}
        try:
            resp = _soap_call(
                _WAYBILL_WSDL, "deactivate_waybill", _WB_NS,
                {"su": self.su, "sp": self.sp, "waybill_id": waybill_id}
            )
            status = _xml_text(resp, "STATUS")
            return {"success": status == "0", "status": status}
        except Exception as exc:
            return {"success": False, "error": str(exc)[:200]}

    def get_waybill_types(self) -> list:
        """Return waybill type lookup from RS.ge or local cache."""
        if self.mode == "demo":
            return [{"id": k, "name": v} for k, v in WAYBILL_TYPES.items()]
        try:
            resp = _soap_call(
                _WAYBILL_WSDL, "get_waybill_types", _WB_NS,
                {"su": self.su, "sp": self.sp}
            )
            return [{"id": _xml_text(t, "ID"), "name": _xml_text(t, "NAME")}
                    for t in resp.iter("WAYBILL_TYPE")]
        except Exception as exc:
            log.warning("[RS.GE] get_waybill_types failed: %s", exc)
            return [{"id": k, "name": v} for k, v in WAYBILL_TYPES.items()]

    def get_waybill_units(self) -> list:
        """Return units of measure from RS.ge."""
        if self.mode == "demo":
            return [{"id": 1, "name": "ცალი"}, {"id": 2, "name": "კგ"},
                    {"id": 3, "name": "ლიტრი"}, {"id": 4, "name": "მ²"},
                    {"id": 99, "name": "სხვა"}]
        try:
            resp = _soap_call(
                _WAYBILL_WSDL, "get_waybill_units", _WB_NS,
                {"su": self.su, "sp": self.sp}
            )
            return [{"id": _xml_text(u, "ID"), "name": _xml_text(u, "NAME")}
                    for u in resp.iter("WAYBILL_UNIT")]
        except Exception as exc:
            log.warning("[RS.GE] get_waybill_units failed: %s", exc)
            return []

    def check_service_user(self) -> dict:
        """Verify RS.ge service credentials (chek_service_user)."""
        try:
            resp = _soap_call(
                _WAYBILL_WSDL, "chek_service_user", _WB_NS,
                {"su": self.su, "sp": self.sp}
            )
            un_id    = _xml_text(resp, "un_id") or _xml_text(resp, "UN_ID")
            s_uid    = _xml_text(resp, "s_user_id") or _xml_text(resp, "S_USER_ID")
            # ASMX returns bool in Result element
            result_el = resp.find("chek_service_userResult")
            valid = (result_el is not None and (result_el.text or "").lower() == "true")
            if not valid and (un_id or s_uid):
                valid = True  # some versions return un_id directly
            return {"valid": valid, "un_id": un_id, "s_user_id": s_uid}
        except Exception as exc:
            return {"valid": False, "error": str(exc)[:200]}

    # ── Invoice ──────────────────────────────────────────────────────────────

    def save_invoice(self, invoice: dict) -> dict:
        """Submit a tax invoice (ანგარიშ-ფაქტურა) to RS.ge invoice service.

        invoice keys:
          user_id, invoice_id (0=new), operation_date, seller_un_id,
          buyer_un_id, overhead_no, overhead_dt, su, sp
        """
        if self.mode == "demo":
            inv_id = f"INV-DEMO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            log.info("[RS.GE] DEMO invoice: %s", inv_id)
            return self._build_success(inv_id)
        try:
            op_date = (invoice.get("operation_date")
                       or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))
            params = {
                "user_id":      invoice.get("user_id", ""),
                "invois_id":    invoice.get("invoice_id", 0),
                "operation_date": op_date,
                "seller_un_id": invoice.get("seller_un_id", self.un_id),
                "buyer_un_id":  invoice.get("buyer_un_id", ""),
                "overhead_no":  invoice.get("overhead_no", ""),
                "overhead_dt":  invoice.get("overhead_dt", op_date),
                "b_s_user_id":  invoice.get("b_s_user_id", ""),
                "su":           self.su,
                "sp":           self.sp,
            }
            resp = _soap_call(_INVOICE_WSDL, "save_invoice", _INV_NS, params)
            result_el = resp.find("save_invoiceResult")
            ok = result_el is not None and (result_el.text or "").lower() == "true"
            inv_id_out = resp.find("invois_id")
            inv_id_val = (inv_id_out.text if inv_id_out is not None else "")
            if ok:
                return self._build_success(inv_id_val)
            return self._build_error("RS.ge save_invoice returned false")
        except Exception as exc:
            log.warning("[RS.GE] save_invoice failed: %s", exc)
            return self._build_error(str(exc)[:200])

    def get_user_invoices(self, limit: int = 50) -> list:
        """Fetch invoice list for the service user."""
        if self.mode == "demo":
            return []
        try:
            resp = _soap_call(
                _INVOICE_WSDL, "get_user_invoices", _INV_NS,
                {"su": self.su, "sp": self.sp, "page_size": limit, "page_no": 1}
            )
            invoices = []
            for inv in resp.iter("INVOICE"):
                invoices.append({
                    "id":             _xml_text(inv, "ID"),
                    "invoice_no":     _xml_text(inv, "INVOICE_NUMBER"),
                    "status":         _xml_text(inv, "STATUS"),
                    "buyer_tin":      _xml_text(inv, "BUYER_TIN"),
                    "buyer_name":     _xml_text(inv, "BUYER_NAME"),
                    "operation_date": _xml_text(inv, "OPERATION_DATE"),
                    "total":          _xml_text(inv, "TOTAL"),
                    "vat":            _xml_text(inv, "VAT"),
                })
            return invoices[:limit]
        except Exception as exc:
            log.warning("[RS.GE] get_user_invoices failed: %s", exc)
            return []

    # ── TaxPayer (REST) ──────────────────────────────────────────────────────

    def verify_taxpayer(self, inn: str) -> dict:
        """Verify taxpayer INN via RS.ge public API (no auth required)."""
        inn = inn.strip()
        if not inn.isdigit() or len(inn) not in (9, 11):
            return {"valid": False, "inn": inn,
                    "reason": "INN must be 9 digits (legal) or 11 digits (individual)"}
        try:
            r = requests.post(_TAXPAYER_REST, json={"IdentCode": inn},
                              timeout=10, verify=True)
            if r.status_code != 200:
                return {"valid": False, "inn": inn,
                        "reason": f"RS.ge returned HTTP {r.status_code}"}
            data = r.json()
            if isinstance(data, list) and data:
                d = data[0]
                return {
                    "valid":              True,
                    "inn":                inn,
                    "full_name":          d.get("FullName", ""),
                    "status":             d.get("Status", ""),
                    "registered_subject": d.get("RegisteredSubject", ""),
                    "vat_payer":          d.get("VatPayer", ""),
                    "start_date":         d.get("StartDate", ""),
                    "mortgage":           d.get("Mortgage", ""),
                    "sequestration":      d.get("Sequestration", ""),
                    "additional_status":  d.get("AdditionalStatus", ""),
                    "non_resident":       d.get("NonResident", ""),
                }
            # Error response: {"Status": -1, "Message": "..."}
            if isinstance(data, dict):
                return {"valid": False, "inn": inn,
                        "reason": data.get("Message", "Not registered")}
            return {"valid": False, "inn": inn, "reason": "Unknown response"}
        except Exception as exc:
            log.warning("[RS.GE] verify_taxpayer failed inn=%s: %s", inn, exc)
            return {"valid": False, "inn": inn, "reason": str(exc)[:200]}
