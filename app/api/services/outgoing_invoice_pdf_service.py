"""
app/api/services/outgoing_invoice_pdf_service.py

PDF generation helpers for outgoing invoices (NSD-style Georgian format).
Called exclusively from app/api/routes_outgoing.py.
"""
from __future__ import annotations

import logging

from app.api.db import get_db

log = logging.getLogger(__name__)


def _load_tenant_signature(tenant_id: str):
    """Return signature bytes from DB, or None."""
    try:
        import base64
        conn = get_db(tenant_id)
        cur = conn.cursor()
        cur.execute("SELECT signature_b64 FROM tenants WHERE tenant_id=%s", (tenant_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row or not row[0]:
            log.info("sig_load tenant=%s → not found", tenant_id)
            return None
        b64 = row[0]
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        data = base64.b64decode(b64)
        log.info("sig_load tenant=%s → %d bytes", tenant_id, len(data))
        return data
    except Exception as _e:
        log.warning("sig_load failed tenant=%s: %s", tenant_id, _e)
        return None


def _load_tenant_stamp(tenant_id: str):
    """Return stamp bytes from DB, or None."""
    try:
        import base64
        conn = get_db(tenant_id)
        cur = conn.cursor()
        cur.execute("SELECT stamp_b64 FROM tenants WHERE tenant_id=%s", (tenant_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row or not row[0]:
            return None
        b64 = row[0]
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        return base64.b64decode(b64)
    except Exception as _e:
        log.warning("stamp_load failed tenant=%s: %s", tenant_id, _e)
        return None


def _remove_bg(image_bytes: bytes):
    """Remove paper background using PIL autocontrast + threshold.

    autocontrast stretches any paper color (grey, beige, yellow, dimly-lit)
    to near-white, then a fixed threshold at 180 cleanly separates ink from paper.
    Works for scans and smartphone photos under any lighting.
    """
    import io as _io
    import numpy as _np
    from PIL import Image as _PILImage, ImageOps as _ImageOps

    orig = _PILImage.open(_io.BytesIO(image_bytes)).convert("RGBA")
    arr  = _np.array(orig, dtype=_np.uint8)

    grey_norm = _np.array(
        _ImageOps.autocontrast(orig.convert("L"), cutoff=2),
        dtype=float,
    )

    hard = grey_norm > 180
    soft = (grey_norm > 140) & ~hard

    alpha = arr[:, :, 3].astype(float)
    alpha[hard] = 0
    alpha[soft] = ((180 - grey_norm[soft]) / 40 * 255).clip(0, 255)
    arr[:, :, 3] = alpha.astype(_np.uint8)

    result = _PILImage.fromarray(arr)
    bbox = result.getbbox()
    if bbox:
        result = result.crop(bbox)
    return result


def _build_nsd_pdf(inv: dict, signature_bytes: bytes = None, stamp_bytes: bytes = None) -> bytes:
    """Generate NSD-style Georgian invoice PDF with colors and styled table."""
    import io, json as _json
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors

    FONT = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"
    try:
        import os
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        _paths = {
            "DejaVuSans": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "DejaVuSans-Bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        }
        _ok = 0
        for _n, _fp in _paths.items():
            if os.path.exists(_fp):
                try:
                    pdfmetrics.registerFont(TTFont(_n, _fp))
                    _ok += 1
                except Exception as e:
                    log.warning("unexpected error: %s", e)
        if _ok == 2:
            FONT = "DejaVuSans"
            FONT_BOLD = "DejaVuSans-Bold"
    except Exception as e:
        log.warning("unexpected error: %s", e)

    line_items = inv.get("line_items") or []
    if isinstance(line_items, str):
        line_items = _json.loads(line_items)

    NAVY        = colors.HexColor("#1e3a5f")
    NAVY_LIGHT  = colors.HexColor("#2d5f9e")
    STRIPE      = colors.HexColor("#eef4fb")
    BOX_BG      = colors.HexColor("#dce8f5")
    TOTAL_BG    = colors.HexColor("#d0e4f5")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    ML = 38
    MR = w - 38
    CW = MR - ML

    inv_type = inv.get("invoice_type", "service")

    c.setFillColor(NAVY)
    c.setFont(FONT_BOLD, 26)
    c.drawRightString(MR, h - 48, "INVOICE")

    y = h - 48
    c.setFillColor(colors.black)
    c.setFont(FONT_BOLD, 13)
    c.drawString(ML, y, inv.get("seller_name") or "")
    c.setFont(FONT, 9)
    for lbl, key in [
        ("მისამართი: ", "seller_address"),
        ("საიდ. კოდი: ", "seller_inn"),
        ("ტელ: ", "seller_phone"),
        ("ბანკი: ", "seller_bank"),
        ("SWIFT CODE: ", "seller_swift"),
        ("ა/ა: ", "seller_account"),
    ]:
        val = inv.get(key) or ""
        if val:
            y -= 13
            c.drawString(ML, y, lbl + val)

    BH, BW = 34, 93
    box_y0 = h - 60 - BH
    bx0 = MR - 3 * BW
    def _fmt_date(d):
        s = str(d or "")[:10]
        return f"{s[8:10]}.{s[5:7]}.{s[:4]}" if len(s) == 10 and s[4] == "-" else s

    lv_pairs = [
        ("თარიღი",       _fmt_date(inv.get("invoice_date"))),
        ("ინვოისი #",    inv.get("invoice_number") or "DRAFT"),
        ("მიწ. თარიღი",  _fmt_date(inv.get("delivery_date"))),
    ]
    for i, (lbl, val) in enumerate(lv_pairs):
        bx = bx0 + i * BW
        c.setFillColor(BOX_BG)
        c.setStrokeColor(NAVY)
        c.setLineWidth(0.8)
        c.rect(bx, box_y0, BW, BH, fill=1, stroke=1)
        c.setFillColor(NAVY)
        c.setFont(FONT_BOLD, 7.5)
        c.drawCentredString(bx + BW / 2, box_y0 + BH / 2 + 4, lbl)
        c.setFillColor(colors.black)
        c.setFont(FONT_BOLD if i == 1 else FONT, 9)
        c.drawCentredString(bx + BW / 2, box_y0 + 6, val)

    sep_y = min(y - 10, box_y0 - 10)
    c.setStrokeColor(NAVY)
    c.setLineWidth(1.4)
    c.line(ML, sep_y, MR, sep_y)

    title_txt = "საქონლის ზედნადები / ინვოისი" if inv_type == "goods" else "მომსახურეობის ინვოისი"
    c.setFillColor(NAVY)
    c.setFont(FONT_BOLD, 11)
    c.drawString(ML, sep_y - 14, title_txt)
    c.setLineWidth(0.5)
    c.line(ML, sep_y - 22, MR, sep_y - 22)

    bar_y = sep_y - 40
    c.setFillColor(NAVY)
    c.setStrokeColor(NAVY)
    c.rect(ML, bar_y, CW, 16, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(FONT_BOLD, 9)
    c.drawString(ML + 6, bar_y + 4, "მყიდველი")

    by = bar_y - 13
    c.setFillColor(colors.black)
    c.setFont(FONT_BOLD, 9)
    c.drawString(ML + 4, by, "კომპანია: " + (inv.get("buyer_name") or ""))
    c.setFont(FONT, 9)
    for lbl, key in [
        ("საიდ. კოდი: ", "buyer_inn"),
        ("მისამართი: ",  "buyer_address"),
        ("ტელეფონი: ",   "buyer_phone"),
    ]:
        val = inv.get(key) or ""
        if val:
            by -= 13
            c.drawString(ML + 4, by, lbl + val)

    tbl_top = by - 16
    ROW_H = 14
    COL_NUM   = 22
    COL_QTY   = 55
    COL_PRICE = 82
    COL_AMT   = 86
    COL_DESC  = CW - COL_NUM - COL_QTY - COL_PRICE - COL_AMT
    cx = [
        ML,
        ML + COL_NUM,
        ML + COL_NUM + COL_DESC,
        ML + COL_NUM + COL_DESC + COL_QTY,
        ML + COL_NUM + COL_DESC + COL_QTY + COL_PRICE,
    ]
    MIN_ROWS = max(len(line_items), 8)
    tbl_h_total = ROW_H + MIN_ROWS * ROW_H

    c.setStrokeColor(NAVY)
    c.setLineWidth(0.8)
    c.rect(ML, tbl_top - tbl_h_total, CW, tbl_h_total, fill=0, stroke=1)

    th_y = tbl_top - ROW_H
    c.setFillColor(NAVY)
    c.rect(ML, th_y, CW, ROW_H, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(FONT_BOLD, 8)
    c.drawCentredString(cx[0] + COL_NUM / 2, th_y + 4, "№")
    c.drawCentredString(cx[1] + COL_DESC / 2, th_y + 4, "დასახელება")
    c.drawRightString(cx[2] + COL_QTY - 4, th_y + 4, "რაოდ.")
    c.drawRightString(cx[3] + COL_PRICE - 4, th_y + 4, "ერთ. ფასი")
    c.drawRightString(cx[4] + COL_AMT - 4, th_y + 4, "თანხა")
    c.setStrokeColor(colors.HexColor("#4a7ab5"))
    c.setLineWidth(0.4)
    for xi in cx[1:]:
        c.line(xi, th_y, xi, th_y + ROW_H)

    row_y = th_y - ROW_H
    c.setLineWidth(0.25)
    for idx, item in enumerate(line_items):
        if row_y < 130:
            c.showPage(); row_y = h - 60
        if idx % 2 == 1:
            c.setFillColor(STRIPE)
            c.rect(ML + 1, row_y, CW - 2, ROW_H, fill=1, stroke=0)
        desc = str(item.get("description") or "")
        qty   = float(item.get("qty") or item.get("quantity") or 1)
        price = float(item.get("unit_price") or item.get("price") or item.get("amount") or 0)
        amt   = qty * price
        if len(desc) > 44: desc = desc[:43] + "…"
        c.setFillColor(colors.black)
        c.setFont(FONT, 8)
        c.drawCentredString(cx[0] + COL_NUM / 2, row_y + 4, str(idx + 1))
        c.drawString(cx[1] + 3, row_y + 4, desc)
        c.drawRightString(cx[2] + COL_QTY - 4, row_y + 4, f"{qty:g}")
        c.drawRightString(cx[3] + COL_PRICE - 4, row_y + 4, f"{price:.2f}")
        c.drawRightString(cx[4] + COL_AMT - 4, row_y + 4, f"{amt:.2f}")
        c.setStrokeColor(colors.HexColor("#c0d4e8"))
        c.line(ML, row_y, MR, row_y)
        for xi in cx[1:]:
            c.line(xi, row_y, xi, row_y + ROW_H)
        row_y -= ROW_H

    while row_y > tbl_top - tbl_h_total + ROW_H:
        c.setStrokeColor(colors.HexColor("#ccdde8"))
        c.setLineWidth(0.2)
        c.line(ML, row_y, MR, row_y)
        c.setFillColor(colors.HexColor("#aaaaaa"))
        c.setFont(FONT, 7)
        c.drawRightString(cx[4] + COL_AMT - 4, row_y + 4, "-")
        for xi in cx[1:]:
            c.line(xi, row_y, xi, row_y + ROW_H)
        row_y -= ROW_H

    _CURRENCY_SYMBOLS = {
        "GEL": "₾", "USD": "$", "EUR": "€",
        "GBP": "£", "TRY": "₺", "RUB": "₽", "CHF": "Fr",
    }
    currency = (inv.get("currency") or "GEL").upper()
    csym = _CURRENCY_SYMBOLS.get(currency, currency)
    exchange_rate = inv.get("exchange_rate")

    c.drawRightString(cx[4] + COL_AMT - 4, th_y + 4, f"თანხა ({csym})")

    subtotal = float(inv.get("subtotal") or 0)
    vat      = float(inv.get("vat_amount") or 0)
    total    = float(inv.get("total_amount") or 0)
    tot_y = row_y - 10
    tx = cx[3]

    def _trow(lbl, txt, bold=False):
        nonlocal tot_y
        c.setFillColor(NAVY if bold else colors.black)
        c.setFont(FONT_BOLD if bold else FONT, 9 if not bold else 10)
        c.drawString(tx, tot_y, lbl)
        c.drawRightString(MR, tot_y, txt)
        tot_y -= 14

    _trow("ფასი:", f"{subtotal:.2f} {csym}")
    _trow("ფასდაკლება:", f"0.00 {csym}")
    _trow("სხვაობა:", f"{subtotal:.2f} {csym}")
    _trow("დღგ (18%):", f"{vat:.2f} {csym}")
    if currency != "GEL" and exchange_rate:
        _trow(f"კურსი ({currency}/GEL):", f"{exchange_rate:.4f}")
        _trow("ჯამი GEL:", f"{total * exchange_rate:.2f} ₾")
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.8)
    c.line(tx, tot_y + 11, MR, tot_y + 11)
    c.setFillColor(TOTAL_BG)
    c.rect(tx, tot_y - 3, MR - tx, 16, fill=1, stroke=0)
    _trow("ჯ ა მ ი:", f"{total:.2f} {csym}", bold=True)

    import io as _io
    from reportlab.lib.utils import ImageReader

    STAMP_SIZE  = 90
    SIG_MAX_H   = 36
    SIG_MAX_W   = 140

    sig_line_y = max(tot_y - 38, STAMP_SIZE + 48)

    c.setStrokeColor(colors.HexColor("#c0c0c0"))
    c.setLineWidth(0.4)
    c.line(ML, sig_line_y + 18, MR, sig_line_y + 18)

    c.setFillColor(colors.black)
    c.setFont(FONT, 9)
    dir_label     = "დირექტორი:"
    dir_label_w   = 63

    c.drawString(ML, sig_line_y, dir_label)

    c.setStrokeColor(colors.black)
    c.setLineWidth(0.5)
    sig_line_x0 = ML + dir_label_w + 2
    sig_line_x1 = ML + dir_label_w + SIG_MAX_W + 4
    c.line(sig_line_x0, sig_line_y - 2, sig_line_x1, sig_line_y - 2)

    if signature_bytes:
        try:
            pil_sig = _remove_bg(signature_bytes)
            png_buf = _io.BytesIO(); pil_sig.save(png_buf, format="PNG"); png_buf.seek(0)
            sig_img = ImageReader(png_buf)
            sw, sh = sig_img.getSize()
            scale = min(SIG_MAX_W / max(sw, 1), SIG_MAX_H / max(sh, 1), 1.0)
            dw, dh = sw * scale, sh * scale
            c.drawImage(sig_img,
                        sig_line_x0,
                        sig_line_y - dh * 0.55,
                        width=dw, height=dh,
                        preserveAspectRatio=True, mask="auto")
            log.info("sig embedded %.0fx%.0f", dw, dh)
        except Exception as _se:
            log.warning("sig embed failed: %s", _se)

    stamp_cx = ML + CW * 0.82
    stamp_bottom = sig_line_y - STAMP_SIZE + 14
    stamp_left   = stamp_cx - STAMP_SIZE / 2

    if stamp_bytes:
        try:
            pil_stamp = _remove_bg(stamp_bytes)
            png_buf2 = _io.BytesIO(); pil_stamp.save(png_buf2, format="PNG"); png_buf2.seek(0)
            stamp_img = ImageReader(png_buf2)
            stw, sth = stamp_img.getSize()
            scale_s = min(STAMP_SIZE / max(stw, 1), STAMP_SIZE / max(sth, 1), 1.0)
            dsw, dsh = stw * scale_s, sth * scale_s
            off_x = (STAMP_SIZE - dsw) / 2
            off_y = (STAMP_SIZE - dsh) / 2
            c.drawImage(stamp_img,
                        stamp_left + off_x, stamp_bottom + off_y,
                        width=dsw, height=dsh,
                        preserveAspectRatio=True, mask="auto")
            log.info("stamp embedded %.0fx%.0f", dsw, dsh)
        except Exception as _ste:
            log.warning("stamp embed failed: %s", _ste)
            c.setFillColor(colors.HexColor("#999999"))
            c.setFont(FONT, 8)
            c.drawCentredString(stamp_cx, sig_line_y - 8, "ბეჭედი")
    else:
        c.setFillColor(colors.HexColor("#999999"))
        c.setFont(FONT, 8)
        c.drawCentredString(stamp_cx, sig_line_y - 8, "ბეჭედი")

    if inv.get("comment"):
        c.setFillColor(colors.black)
        c.setFont(FONT, 8)
        comment_y = min(sig_line_y - 28, stamp_bottom - 10)
        c.drawString(ML, comment_y, f"კომენტარი: {str(inv['comment'])[:120]}")

    c.save()
    buf.seek(0)
    return buf.read()
