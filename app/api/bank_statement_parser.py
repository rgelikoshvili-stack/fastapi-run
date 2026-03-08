import io, math, csv
import pandas as pd
import xml.etree.ElementTree as ET

NS = {"g": "http://www.mygemini.com/schemas/mygemini"}

def _clean(v):
    if v is None: return None
    try:
        if isinstance(v, float) and math.isnan(v): return None
    except: pass
    if hasattr(v, "isoformat"): return v.isoformat()
    s = str(v).strip()
    return s if s and s.lower() not in ("nan", "") else None

def _amount(v):
    if v is None: return None
    try: return float(str(v).replace(",", "").replace(" ", ""))
    except: return None

def _normalize(row):
    paid_out = _amount(row.get("paid_out"))
    paid_in  = _amount(row.get("paid_in"))
    amount   = _amount(row.get("amount"))
    # single amount column logic
    if paid_out is None and paid_in is None and amount is not None:
        if amount < 0:
            paid_out = abs(amount)
        elif amount > 0:
            paid_in = amount
        else:
            row["review_required"] = True
    row["paid_out"] = paid_out
    row["paid_in"]  = paid_in
    row.pop("amount", None)
    return row

FALLBACK_COLS = {
    "date":         ["date","Date","თარიღი","transaction_date","ValueDate","Document Date"],
    "description":  ["description","Description","დანიშნულება","details","Details","Narrative"],
    "paid_out":     ["paid_out","PaidOut","Paid Out","debit","Debit","გასული თანხა","WithdrawalAmt"],
    "paid_in":      ["paid_in","PaidIn","Paid In","credit","Credit","შემოსული თანხა","DepositAmt"],
    "amount":       ["amount","Amount","თანხა"],
    "partner":      ["partner","Partner","პარტნიორი","Counterparty"],
    "operation_code":["operation_code","OperationCode","ოპ. კოდი","TxnType"],
    "transaction_id":["transaction_id","TransactionId","ტრანზაქციის ID","RefNo"],
}

def _get(row_dict, field):
    for col in FALLBACK_COLS.get(field, []):
        v = row_dict.get(col)
        if v not in (None, "", "nan"): return v
    return None

def parse_csv_bytes(content: bytes):
    try: text = content.decode("utf-8")
    except: text = content.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        r = {f: _get(row, f) for f in FALLBACK_COLS}
        r["source_type"] = "csv"
        rows.append(_normalize(r))
    return rows

def parse_xlsx_bytes(content: bytes):
    xl = pd.ExcelFile(io.BytesIO(content))
    sheet = next((s for s in xl.sheet_names if s != "Summary"), xl.sheet_names[0])
    # TBC Bank: row1=Georgian, row2=English, data from row3 → header=1
    df = pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=1)
    rows = []
    for _, r in df.iterrows():
        rd = {str(k).strip(): _clean(v) for k, v in r.items()}
        row = {f: _get(rd, f) for f in FALLBACK_COLS}
        if not row.get("date") and not row.get("description"): continue
        if not row.get("paid_out") and not row.get("paid_in") and not row.get("amount"): continue
        row["source_type"] = "xlsx"
        rows.append(_normalize(row))
    return rows

def parse_xml_bytes(content: bytes):
    root = ET.fromstring(content)
    rows = []
    for rec in root.findall(".//g:Record", NS):
        def gt(tag):
            x = rec.find(f"g:{tag}", NS)
            return _clean(x.text if x is not None else None)
        row = {
            "date": gt("Date"), "description": gt("Description"),
            "paid_out": gt("PaidOut"), "paid_in": gt("PaidIn"),
            "partner": gt("PartnerName"), "operation_code": gt("OperationCode"),
            "transaction_id": gt("TransactionId"), "source_type": "xml",
        }
        rows.append(_normalize(row))
    return rows
