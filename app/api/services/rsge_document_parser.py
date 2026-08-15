"""app/api/services/rsge_document_parser.py

RS.ge document XML/JSON parser for Sprint 3A.
Parses exports from RS.ge portal: ზედნადები (waybills) and ფაქტურები (tax invoices).
No live RS.ge connection — file-based import only.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional
import xml.etree.ElementTree as ET

log = logging.getLogger(__name__)


def _dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v).replace(",", ".").strip())
    except InvalidOperation:
        return None


def _text(el, *tags) -> Optional[str]:
    """Find first matching tag in element, return stripped text or None."""
    for tag in tags:
        child = el.find(tag)
        if child is not None and child.text:
            return child.text.strip()
    return None


def _parse_waybill_xml_element(wb: ET.Element) -> dict:
    """Parse a single <Waybill> XML element into a flat dict."""
    seller = wb.find("Seller") or wb.find("seller")
    buyer = wb.find("Buyer") or wb.find("buyer")
    car = wb.find("Car") or wb.find("car")
    driver = wb.find("Driver") or wb.find("driver")

    # Line items
    items = []
    goods_el = wb.find("Goods") or wb.find("goods") or wb.find("GoodList")
    if goods_el is not None:
        for good in goods_el:
            items.append({
                "name": _text(good, "Name", "name", "ProductName"),
                "quantity": _text(good, "Quantity", "quantity", "Qty"),
                "unit": _text(good, "UnitOfMeasure", "Unit", "unit"),
                "price": _text(good, "Price", "price", "UnitPrice"),
                "total": _text(good, "Total", "total", "Amount"),
            })

    subtotal = _dec(_text(wb, "GoodsTotalPrice", "SubTotal", "subtotal", "TotalWithoutVAT"))
    vat_amount = _dec(_text(wb, "VATAmount", "VatAmount", "vat_amount", "VATTotal"))
    total_amount = _dec(_text(wb, "TotalAmount", "GrandTotal", "total_amount", "TotalWithVAT"))

    # Infer subtotal if missing
    if subtotal is None and total_amount is not None and vat_amount is not None:
        subtotal = total_amount - vat_amount

    return {
        "waybill_number": _text(wb, "Number", "WaybillNumber", "number", "Id"),
        "waybill_date": _text(wb, "CreateDate", "ActivateDate", "Date", "date"),
        "seller_inn": _text(seller, "Tin", "tin", "INN") if seller is not None else _text(wb, "SellerTin"),
        "seller_name": _text(seller, "Name", "name") if seller is not None else _text(wb, "SellerName"),
        "buyer_inn": _text(buyer, "Tin", "tin", "INN") if buyer is not None else _text(wb, "BuyerTin"),
        "buyer_name": _text(buyer, "Name", "name") if buyer is not None else _text(wb, "BuyerName"),
        "transport_from": _text(wb, "TransportationStartAddress", "StartAddress", "transport_from"),
        "transport_to": _text(wb, "TransportationEndAddress", "EndAddress", "transport_to"),
        "vehicle_number": _text(car, "Number", "number") if car is not None else _text(wb, "CarNumber"),
        "driver_name": _text(driver, "Name", "FullName") if driver is not None else _text(wb, "DriverName"),
        "line_items": items,
        "subtotal": subtotal,
        "vat_amount": vat_amount,
        "total_amount": total_amount,
    }


def _parse_tax_invoice_xml_element(inv: ET.Element) -> dict:
    """Parse a single <Invoice> XML element into a flat dict."""
    seller = inv.find("Seller") or inv.find("seller")
    buyer = inv.find("Buyer") or inv.find("buyer")

    items = []
    items_el = inv.find("Items") or inv.find("Goods") or inv.find("Lines")
    if items_el is not None:
        for item in items_el:
            items.append({
                "name": _text(item, "Name", "name", "ProductName", "GoodName"),
                "quantity": _text(item, "Quantity", "quantity", "Qty"),
                "unit": _text(item, "Unit", "UnitOfMeasure", "unit"),
                "price": _text(item, "Price", "UnitPrice", "price"),
                "total": _text(item, "Total", "Amount", "total"),
                "vat": _text(item, "VAT", "VATAmount", "vat"),
            })

    subtotal = _dec(_text(inv, "TotalWithoutVAT", "SubTotal", "GoodsTotalPrice", "subtotal"))
    vat_amount = _dec(_text(inv, "VATTotal", "VATAmount", "vat_amount"))
    total_amount = _dec(_text(inv, "TotalWithVAT", "TotalAmount", "GrandTotal", "total_amount"))

    if subtotal is None and total_amount is not None and vat_amount is not None:
        subtotal = total_amount - vat_amount

    serial = _text(inv, "SerialNumber", "Series", "series")
    number = _text(inv, "Number", "InvoiceNumber", "number", "Id")
    if serial and number:
        full_number = f"{serial}{number}"
    else:
        full_number = number or serial

    return {
        "invoice_number": full_number,
        "invoice_series": serial,
        "invoice_date": _text(inv, "CreateDate", "Date", "InvoiceDate", "date"),
        "seller_inn": _text(seller, "Tin", "tin", "INN") if seller is not None else _text(inv, "SellerTin"),
        "seller_name": _text(seller, "Name", "name") if seller is not None else _text(inv, "SellerName"),
        "buyer_inn": _text(buyer, "Tin", "tin", "INN") if buyer is not None else _text(inv, "BuyerTin"),
        "buyer_name": _text(buyer, "Name", "name") if buyer is not None else _text(inv, "BuyerName"),
        "line_items": items,
        "subtotal": subtotal,
        "vat_amount": vat_amount,
        "total_amount": total_amount,
        "related_waybill_number": _text(inv, "WaybillNumber", "RelatedWaybill", "waybill_number"),
    }


def parse_rsge_waybills(content: bytes) -> list[dict]:
    """
    Parse RS.ge waybill export.
    Supports: XML (single <Waybill> or <Waybills> list), JSON array/object.
    Returns list of parsed waybill dicts.
    """
    text = content.decode("utf-8", errors="replace").strip()

    # JSON path
    if text.startswith("[") or text.startswith("{"):
        try:
            data = json.loads(text)
            items = data if isinstance(data, list) else [data]
            return [_normalise_waybill_json(item) for item in items]
        except json.JSONDecodeError as e:
            log.warning("rsge waybill JSON parse failed: %s", e)
            return []

    # XML path
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        log.warning("rsge waybill XML parse failed: %s", e)
        return []

    # Root is <Waybill>
    tag = root.tag.lower().split("}")[-1]
    if tag in ("waybill", "ზედნადები"):
        return [_parse_waybill_xml_element(root)]

    # Root is <Waybills> container
    results = []
    for child in root:
        child_tag = child.tag.lower().split("}")[-1]
        if child_tag in ("waybill", "ზედნადები", "item"):
            results.append(_parse_waybill_xml_element(child))
    return results


def parse_rsge_tax_invoices(content: bytes) -> list[dict]:
    """
    Parse RS.ge tax invoice export.
    Supports: XML (single <Invoice> or <Invoices> list), JSON.
    Returns list of parsed tax invoice dicts.
    """
    text = content.decode("utf-8", errors="replace").strip()

    if text.startswith("[") or text.startswith("{"):
        try:
            data = json.loads(text)
            items = data if isinstance(data, list) else [data]
            return [_normalise_tax_invoice_json(item) for item in items]
        except json.JSONDecodeError as e:
            log.warning("rsge tax_invoice JSON parse failed: %s", e)
            return []

    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        log.warning("rsge tax_invoice XML parse failed: %s", e)
        return []

    tag = root.tag.lower().split("}")[-1]
    if tag in ("invoice", "ფაქტურა", "taxinvoice"):
        return [_parse_tax_invoice_xml_element(root)]

    results = []
    for child in root:
        child_tag = child.tag.lower().split("}")[-1]
        if child_tag in ("invoice", "ფაქტურა", "taxinvoice", "item"):
            results.append(_parse_tax_invoice_xml_element(child))
    return results


def _normalise_waybill_json(d: dict) -> dict:
    """Normalise camelCase/snake_case JSON waybill into our field names."""
    def g(*keys):
        for k in keys:
            if k in d:
                return d[k]
        return None

    items = g("line_items", "lineItems", "goods", "items") or []
    return {
        "waybill_number": g("waybill_number", "number", "waybillNumber", "Number"),
        "waybill_date": g("waybill_date", "date", "waybillDate", "CreateDate"),
        "seller_inn": g("seller_inn", "sellerInn", "SellerTin"),
        "seller_name": g("seller_name", "sellerName", "SellerName"),
        "buyer_inn": g("buyer_inn", "buyerInn", "BuyerTin"),
        "buyer_name": g("buyer_name", "buyerName", "BuyerName"),
        "transport_from": g("transport_from", "transportFrom", "StartAddress"),
        "transport_to": g("transport_to", "transportTo", "EndAddress"),
        "vehicle_number": g("vehicle_number", "vehicleNumber", "CarNumber"),
        "driver_name": g("driver_name", "driverName", "DriverName"),
        "line_items": items,
        "subtotal": _dec(g("subtotal", "subTotal", "GoodsTotalPrice")),
        "vat_amount": _dec(g("vat_amount", "vatAmount", "VATAmount")),
        "total_amount": _dec(g("total_amount", "totalAmount", "TotalAmount")),
    }


def _normalise_tax_invoice_json(d: dict) -> dict:
    def g(*keys):
        for k in keys:
            if k in d:
                return d[k]
        return None

    items = g("line_items", "lineItems", "items", "goods") or []
    return {
        "invoice_number": g("invoice_number", "number", "invoiceNumber", "Number"),
        "invoice_series": g("invoice_series", "series", "SerialNumber"),
        "invoice_date": g("invoice_date", "date", "invoiceDate", "CreateDate"),
        "seller_inn": g("seller_inn", "sellerInn", "SellerTin"),
        "seller_name": g("seller_name", "sellerName", "SellerName"),
        "buyer_inn": g("buyer_inn", "buyerInn", "BuyerTin"),
        "buyer_name": g("buyer_name", "buyerName", "BuyerName"),
        "line_items": items,
        "subtotal": _dec(g("subtotal", "subTotal", "TotalWithoutVAT")),
        "vat_amount": _dec(g("vat_amount", "vatAmount", "VATTotal")),
        "total_amount": _dec(g("total_amount", "totalAmount", "TotalWithVAT")),
        "related_waybill_number": g("related_waybill_number", "waybillNumber", "WaybillNumber"),
    }
