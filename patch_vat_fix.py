from pathlib import Path
import re

p = Path("main.py")
s = p.read_text(encoding="utf-8")

marker = "# --- VAT normalization (GE) ---"
pos = s.find(marker)
if pos == -1:
    raise SystemExit("❌ Marker not found: " + marker)

# indentation of the marker line
line_start = s.rfind("\n", 0, pos) + 1
indent = re.match(r"[ \t]*", s[line_start:pos]).group(0)

net_total_block = f"""
{indent}# --- NET/TOTAL reconciliation (GE) ---
{indent}# If text contains both NET and TOTAL, force amount=TOTAL and vat=TOTAL-NET
{indent}try:
{indent}    _txt = str((data.get("text") or "")).lower() if isinstance(data, dict) else ""
{indent}    if ("net" in _txt) and ("total" in _txt) and isinstance(result, dict):
{indent}        import re
{indent}        def _num_after(w: str):
{indent}            m = re.search(rf"\\b{w}\\b\\s*[:=]?\\s*([0-9]+(?:\\.[0-9]+)?)", _txt)
{indent}            return float(m.group(1)) if m else None
{indent}        _net = _num_after("net")
{indent}        _total = _num_after("total")
{indent}        if _net is not None and _total is not None and _total >= _net:
{indent}            result["amount"] = _total
{indent}            _vat_amt = round(_total - _net, 2)
{indent}            if isinstance(result.get("vat"), dict):
{indent}                result["vat"]["amount"] = _vat_amt
{indent}            else:
{indent}                result["vat"] = {{"rate": 0.18, "amount": _vat_amt}}
{indent}except Exception:
{indent}    pass

"""

vat_gate_block = f"""
{indent}# --- VAT presence gate ---
{indent}# If VAT is NOT mentioned in text, remove vat from result (set to null)
{indent}try:
{indent}    _txt = str((data.get("text") or "")).lower() if isinstance(data, dict) else ""
{indent}    _vat_mentioned = any(k in _txt for k in ["vat", "დღგ", "iva", "nds", "ნდს"])
{indent}    if isinstance(result, dict) and (not _vat_mentioned):
{indent}        result["vat"] = None
{indent}except Exception:
{indent}    pass

"""

# Insert NET/TOTAL block BEFORE marker (only once)
if "NET/TOTAL reconciliation (GE)" not in s:
    s = s[:line_start] + net_total_block + s[line_start:]

# Insert VAT gate RIGHT AFTER marker line (only once)
if "VAT presence gate" not in s:
    pos2 = s.find(marker)
    endline = s.find("\n", pos2)
    if endline == -1:
        endline = pos2 + len(marker)
    insert_at = endline + 1
    s = s[:insert_at] + vat_gate_block + s[insert_at:]

p.write_text(s, encoding="utf-8")
print("✅ Patch applied: NET/TOTAL + VAT gate.")
