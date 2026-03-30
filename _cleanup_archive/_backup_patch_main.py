from pathlib import Path

p = Path("main.py")
text = p.read_text(encoding="utf-8")

insert_block = '''
# ============================================================
# BANK FILE AUTO-DETECT + CANONICAL NORMALIZATION
# ============================================================

SUPPORTED_BANK_FILE_TYPES = {"pdf", "csv", "xlsx", "docx"}


class CanonicalBankTransaction(BaseModel):
    date: Optional[str] = None
    description: str = ""
    amount: float = 0.0
    currency: Optional[str] = None
    direction: Literal["in", "out", "neutral"] = "neutral"
    counterparty: Optional[str] = None
    source_type: Literal["pdf", "csv", "xlsx", "docx"]
    raw_reference: Optional[str] = None


class AccountingClassifyRequest(BaseModel):
    transaction: Dict[str, Any]


def _normalize_numeric_amount(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if not s:
        return 0.0

    s = s.replace(" ", "")
    s = s.replace("₾", "").replace("$", "").replace("€", "").replace("£", "")

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        if s.count(",") == 1 and s.count(".") == 0:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")

    try:
        return float(s)
    except Exception:
        return 0.0


def detect_bank_file_type(content_bytes: bytes, filename: Optional[str] = None, declared_file_type: Optional[str] = None) -> str:
    if declared_file_type:
        ft = str(declared_file_type).strip().lower()
        if ft in SUPPORTED_BANK_FILE_TYPES:
            return ft

    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in SUPPORTED_BANK_FILE_TYPES:
            return ext

    head = content_bytes[:16]

    if head.startswith(b"%PDF"):
        return "pdf"

    if head.startswith(b"PK"):
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(content_bytes)) as zf:
                names = set(zf.namelist())
                if any(name.startswith("xl/") for name in names):
                    return "xlsx"
                if any(name.startswith("word/") for name in names):
                    return "docx"
        except Exception:
            pass

    try:
        sample = content_bytes[:2048].decode("utf-8-sig", errors="ignore")
        if sample:
            lines = [x for x in sample.splitlines()[:5] if x.strip()]
            joined = "\\n".join(lines)
            if joined.count(",") + joined.count(";") + joined.count("\\t") >= 2:
                return "csv"
    except Exception:
        pass

    raise ValueError("Could not detect file type. Supported: pdf, csv, xlsx, docx")


def canonicalize_bank_transaction(raw: Dict[str, Any], source_type: str, idx: int = 0) -> Dict[str, Any]:
    signed_amount = _normalize_numeric_amount(
        raw.get("amount")
        or raw.get("sum")
        or raw.get("value")
        or raw.get("transaction_amount")
        or 0
    )

    direction = "neutral"
    if signed_amount > 0:
        direction = "in"
    elif signed_amount < 0:
        direction = "out"

    description = (
        raw.get("description")
        or raw.get("details")
        or raw.get("memo")
        or raw.get("narration")
        or ""
    )
    description = str(description).strip()

    currency = raw.get("currency") or raw.get("ccy")
    counterparty = raw.get("counterparty") or raw.get("merchant") or raw.get("company_name")
    raw_reference = (
        raw.get("raw_reference")
        or raw.get("reference")
        or raw.get("id")
        or f"{source_type}-{idx + 1}"
    )

    item = CanonicalBankTransaction(
        date=raw.get("date"),
        description=description,
        amount=abs(signed_amount),
        currency=currency,
        direction=direction,
        counterparty=counterparty,
        source_type=source_type,
        raw_reference=str(raw_reference) if raw_reference is not None else None,
    )

    return item.model_dump()


def canonicalize_statement_transactions(raw_transactions: Any, source_type: str) -> list[Dict[str, Any]]:
    if not isinstance(raw_transactions, list):
        return []

    items = []
    for i, tx in enumerate(raw_transactions):
        if not isinstance(tx, dict):
            continue
        try:
            items.append(canonicalize_bank_transaction(tx, source_type, i))
        except Exception:
            continue
    return items


def classify_transaction_rule_based(tx: Dict[str, Any]) -> Dict[str, Any]:
    text_tx = str(tx.get("description", "")).lower()
    direction = tx.get("direction")

    BANK_ACCOUNT = "BANK_MAIN"
    AR_ACCOUNT = "AR_TRADE"
    AP_ACCOUNT = "AP_TRADE"
    REV_ACCOUNT = "REV_OTHER"
    FEE_EXPENSE = "EXP_BANK_FEES"
    PAYROLL_EXPENSE = "EXP_PAYROLL"
    TAX_ACCOUNT = "TAX_PAYABLE"
    OWNER_ACCOUNT = "OWNER_SETTLEMENT"

    if any(k in text_tx for k in ["fee", "commission", "bank fee", "კომის", "საკომისიო"]):
        return {
            "suggested_category": "bank_fee",
            "suggested_debit_account": FEE_EXPENSE,
            "suggested_credit_account": BANK_ACCOUNT,
            "confidence": 0.93,
            "reason": "Description indicates bank fee / commission."
        }

    if any(k in text_tx for k in ["salary", "payroll", "wage", "ხელფას", "ანაზღაურ"]):
        return {
            "suggested_category": "salary_payment",
            "suggested_debit_account": PAYROLL_EXPENSE,
            "suggested_credit_account": BANK_ACCOUNT,
            "confidence": 0.90,
            "reason": "Description indicates salary / payroll."
        }

    if any(k in text_tx for k in ["tax", "revenue service", "rs.ge", "საგადასახადო", "ბიუჯეტ"]):
        return {
            "suggested_category": "tax_payment",
            "suggested_debit_account": TAX_ACCOUNT,
            "suggested_credit_account": BANK_ACCOUNT,
            "confidence": 0.88,
            "reason": "Description suggests tax-related payment."
        }

    if direction == "in":
        return {
            "suggested_category": "incoming_receipt",
            "suggested_debit_account": BANK_ACCOUNT,
            "suggested_credit_account": AR_ACCOUNT if tx.get("counterparty") else REV_ACCOUNT,
            "confidence": 0.74,
            "reason": "Incoming transaction; likely receipt / income."
        }

    if direction == "out":
        return {
            "suggested_category": "outgoing_payment",
            "suggested_debit_account": AP_ACCOUNT if tx.get("counterparty") else OWNER_ACCOUNT,
            "suggested_credit_account": BANK_ACCOUNT,
            "confidence": 0.68,
            "reason": "Outgoing transaction; likely payment / settlement."
        }

    return {
        "suggested_category": "unclassified",
        "suggested_debit_account": None,
        "suggested_credit_account": None,
        "confidence": 0.35,
        "reason": "Not enough signal to classify."
    }
'''

endpoint_block = '''
@app.post("/accounting/classify", response_model=Dict[str, Any])
def accounting_classify(payload: AccountingClassifyRequest):
    raw_tx = payload.transaction or {}

    source_type = str(raw_tx.get("source_type") or "csv").lower()
    if source_type not in SUPPORTED_BANK_FILE_TYPES:
        source_type = "csv"

    normalized = canonicalize_bank_transaction(raw_tx, source_type)
    classification = classify_transaction_rule_based(normalized)

    store_event({
        "kind": "accounting_classify",
        "source_type": source_type,
        "category": classification.get("suggested_category"),
        "confidence": classification.get("confidence"),
    })

    return {
        "ok": True,
        "transaction": normalized,
        **classification
    }

'''

new_upload_fn = '''
@app.post("/bank/upload", response_model=Dict[str, Any])
def upload_bank_statement(payload: Dict[str, Any]):
    """Upload and parse bank statement (PDF/CSV/XLSX/DOCX) with auto-detect + canonical normalization"""

    declared_file_type = payload.get("file_type")
    file_content = payload.get("file_content")
    bank_name = payload.get("bank_name", "Unknown")
    filename = payload.get("filename")

    if not file_content:
        return {
            "ok": False,
            "error": "file_content is required (base64 encoded)",
            "total_transactions": 0
        }

    try:
        import base64
        content_bytes = base64.b64decode(file_content)

        resolved_file_type = detect_bank_file_type(
            content_bytes=content_bytes,
            filename=filename,
            declared_file_type=declared_file_type
        )

        if resolved_file_type == "pdf":
            result = parse_pdf_bank_statement(content_bytes, bank_name)
        elif resolved_file_type == "csv":
            result = parse_csv_bank_statement(content_bytes, bank_name)
        elif resolved_file_type == "xlsx":
            result = parse_excel_bank_statement(content_bytes, bank_name)
        elif resolved_file_type == "docx":
            text_doc = extract_docx_text(content_bytes)
            result = {
                "ok": True,
                "transactions": [],
                "total_transactions": 0,
                "parse_method": "docx",
                "message": "DOCX parsed as text document",
                "chars": len(text_doc),
                "preview": text_doc[:1500],
            }
        else:
            return {
                "ok": False,
                "error": f"Unsupported file type: {resolved_file_type}",
                "total_transactions": 0
            }

        raw_transactions = result.get("transactions", [])
        canonical_transactions = canonicalize_statement_transactions(raw_transactions, resolved_file_type)

        result["raw_transactions"] = raw_transactions
        result["transactions"] = canonical_transactions
        result["total_transactions"] = len(canonical_transactions)
        result["statement_id"] = str(uuid.uuid4())
        result["bank_name"] = bank_name
        result["file_type"] = resolved_file_type

        BANK_STATEMENTS.append(result)

        store_event({
            "kind": "bank_statement_uploaded",
            "statement_id": result["statement_id"],
            "file_type": resolved_file_type,
            "bank_name": bank_name,
            "total_transactions": result.get("total_transactions", 0)
        })

        return result

    except Exception as e:
        return {
            "ok": False,
            "error": f"Upload failed: {str(e)}",
            "total_transactions": 0
        }
'''

if "SUPPORTED_BANK_FILE_TYPES" not in text:
    marker = 'BANK_STATEMENTS: list[Dict[str, Any]] = []'
    text = text.replace(marker, marker + "\\n" + insert_block)

if '@app.post("/accounting/classify"' not in text:
    marker = '@app.post("/bridge/accounting/draft/queue", response_model=Dict[str, Any])'
    text = text.replace(marker, endpoint_block + marker)

start = text.find('@app.post("/bank/upload", response_model=Dict[str, Any])')
if start != -1:
    end = text.find('@app.get("/bank/statements")', start)
    if end != -1:
        text = text[:start] + new_upload_fn + "\\n\\n" + text[end:]

text = text.replace('def parse_amount(value: any) -> float:', 'def parse_amount(value: Any) -> float:')
text = text.replace('transactions: list[BankTransaction] = []', 'transactions: list[BankTransaction] = Field(default_factory=list)')

p.write_text(text, encoding="utf-8")
print("PATCH_APPLIED")
