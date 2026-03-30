# main.py - FIXED Bridge Hub v1.0
import os
import uuid
import json
import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Literal

import requests
import fitz
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field, ConfigDict
def rule_classify(text: str):
    t = (text or "").lower()

    # áƒáƒ¤áƒ˜áƒ¡áƒ˜áƒ¡ áƒ¡áƒáƒ¥áƒáƒœáƒ”áƒšáƒ˜ / áƒ™áƒáƒœáƒªáƒ”áƒšáƒáƒ áƒ˜áƒ
    if ("a4" in t and ("áƒ¥áƒáƒ¦áƒáƒšáƒ“áƒ˜" in t or "paper" in t)) or ("áƒ™áƒáƒœáƒªáƒ”áƒš" in t):
        return {
            "category": "OFFICE_SUPPLIES",
            "account_code": "7410",
            "vat_rate": 0.18,
            "confidence": 0.95,
        }

    # áƒ¡áƒáƒ¬áƒ•áƒáƒ•áƒ˜
    if "áƒ‘áƒ”áƒœáƒ–" in t or "diesel" in t or "áƒ¡áƒáƒ¬áƒ•áƒáƒ•" in t:
        return {
            "category": "FUEL",
            "account_code": "7420",
            "vat_rate": 0.18,
            "confidence": 0.9,
        }

    return None

app = FastAPI(
    title="Bridge Hub",
    version="1.0.0",
    description="Central message exchange for AI services"
)

FromTo = Literal["manus", "charjibit", "bridge", "balance", "1c", "email", "voice"]
MsgType = Literal["event", "request", "response", "error"]


class Envelope(BaseModel):
    messageId: str = Field(default_factory=lambda: str(uuid.uuid4()))
    threadId: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_: FromTo = Field(alias="from")
    to: FromTo
    type: MsgType
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    payload: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True)

    def model_dump_alias(self):
        return self.model_dump(by_alias=True)


class RunRequest(BaseModel):
    input_text: Optional[str] = None
    messageId: Optional[str] = None
    envelope: Optional[Envelope] = None
    mode: Literal["openai_only", "manus_only", "openai_then_manus"] = "openai_only"
    context: Optional[Dict[str, Any]] = None


class RunResponse(BaseModel):
    ok: bool
    envelope: Envelope
    routed: Dict[str, Any] = Field(default_factory=dict)


PROCESSED_MESSAGES = set()


def compute_payload_hash(payload: Dict[str, Any]) -> str:
    json_str = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(json_str.encode()).hexdigest()


def get_stable_dedup_key(payload: Dict[str, Any]) -> str:
    if isinstance(payload, dict):
        if "event_id" in payload:
            return str(payload["event_id"])
        if "id" in payload:
            return str(payload["id"])
        if "messageId" in payload:
            return str(payload["messageId"])
    return compute_payload_hash(payload)


def is_duplicate(message_id: str) -> bool:
    return message_id in PROCESSED_MESSAGES


def mark_processed(message_id: str) -> None:
    PROCESSED_MESSAGES.add(message_id)


def call_openai(user_text: str) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    
    if not api_key:
        return {
            "provider": "openai",
            "ok": False,
            "error": "OPENAI_API_KEY not set",
            "mode": "mock",
            "text": f"[Mock] Processed: {user_text[:50]}...",
        }

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini" ),
        "messages": [
            {"role": "system", "content": "You are a helpful routing assistant. Respond briefly."},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.2,
        "max_tokens": 500,
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        if r.status_code != 200:
            error_msg = r.text[:200] if r.text else f"HTTP {r.status_code}"
            return {
                "provider": "openai",
                "ok": False,
                "error": error_msg,
                "mode": "error",
                "status_code": r.status_code,
            }
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        return {
            "provider": "openai",
            "ok": True,
            "text": text,
            "mode": "live",
        }
    except requests.exceptions.Timeout:
        return {
            "provider": "openai",
            "ok": False,
            "error": "Request timeout (30s)",
            "mode": "error",
        }
    except Exception as e:
        return {
            "provider": "openai",
            "ok": False,
            "error": str(e)[:200],
            "mode": "error",
        }


def call_manus(payload: Dict[str, Any]) -> Dict[str, Any]:
    manus_url = os.getenv("MANUS_WEBHOOK_URL", "").strip()
    
    if not manus_url:
        return {
            "provider": "manus",
            "ok": False,
            "error": "MANUS_WEBHOOK_URL not set",
            "mode": "mock",
        }

    try:
        r = requests.post(manus_url, json=payload, timeout=30)
        if r.status_code >= 300:
            return {
                "provider": "manus",
                "ok": False,
                "error": r.text[:200],
                "mode": "error",
                "status_code": r.status_code,
            }
        return {
            "provider": "manus",
            "ok": True,
            "data": r.json() if r.text else {"status": "ok"},
            "mode": "live",
        }
    except requests.exceptions.Timeout:
        return {
            "provider": "manus",
            "ok": False,
            "error": "Request timeout (30s)",
            "mode": "error",
        }
    except Exception as e:
        return {
            "provider": "manus",
            "ok": False,
            "error": str(e)[:200],
            "mode": "error",
        }


IN_MEMORY_LOG: list[dict] = []


def store_event(event: Dict[str, Any]) -> None:
    event["stored_at"] = datetime.now(timezone.utc).isoformat()
    IN_MEMORY_LOG.append(event)
    if len(IN_MEMORY_LOG) > 1000:
        IN_MEMORY_LOG.pop(0)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "bridge-hub",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/bridge/envelope", response_model=RunResponse)
def ingest_envelope(env: Envelope):
    if is_duplicate(env.messageId):
        store_event({
            "kind": "duplicate_detected",
            "messageId": env.messageId,
            "threadId": env.threadId,
            "action": "ignored",
        })
        out_env = Envelope(
            **{
                "from": "bridge",
                "to": env.from_,
                "type": "response",
                "threadId": env.threadId,
                "payload": {
                    "received": True,
                    "originalMessageId": env.messageId,
                    "status": "duplicate_ignored",
                },
            }
        )
        return RunResponse(ok=True, envelope=out_env, routed={"action": "duplicate"})

    mark_processed(env.messageId)

    store_event({
        "kind": "incoming_envelope",
        "messageId": env.messageId,
        "threadId": env.threadId,
        "from": env.from_,
        "to": env.to,
        "type": env.type,
        "payload_keys": list(env.payload.keys()) if isinstance(env.payload, dict) else [],
    })

    out_env = Envelope(
        **{
            "from": "bridge",
            "to": env.from_,
            "type": "response",
            "threadId": env.threadId,
            "payload": {
                "received": True,
                "originalMessageId": env.messageId,
                "status": "stored",
            },
        }
    )

    store_event({
        "kind": "outgoing_envelope",
        "messageId": out_env.messageId,
        "threadId": out_env.threadId,
        "from": out_env.from_,
        "to": out_env.to,
        "type": out_env.type,
    })

    return RunResponse(ok=True, envelope=out_env, routed={"action": "stored"})


@app.post("/bridge/run", response_model=RunResponse)
def bridge_run(req: RunRequest):
    if req.envelope is None:
        if not req.input_text:
            raise HTTPException(status_code=400, detail="Provide input_text or envelope")

        env_in = Envelope(
            **{
                "messageId": req.messageId or str(uuid.uuid4()),
                "from": "manus",
                "to": "bridge",
                "type": "request",
                "payload": {"text": req.input_text, "context": req.context or {}},
            }
        )
    else:
        env_in = req.envelope

    if is_duplicate(env_in.messageId):
        store_event({
            "kind": "bridge_run_duplicate",
            "messageId": env_in.messageId,
            "mode": req.mode,
        })
        out_env = Envelope(
            **{
                "from": "bridge",
                "to": env_in.from_,
                "type": "response",
                "threadId": env_in.threadId,
                "payload": {"status": "duplicate_ignored"},
            }
        )
        return RunResponse(ok=True, envelope=out_env, routed={"action": "duplicate"})

    mark_processed(env_in.messageId)

    store_event({
        "kind": "bridge_run_in",
        "messageId": env_in.messageId,
        "threadId": env_in.threadId,
        "mode": req.mode,
        "from": env_in.from_,
    })

    routed: Dict[str, Any] = {}

    user_text = ""
    if isinstance(env_in.payload, dict):
        user_text = str(env_in.payload.get("text", "")) or str(env_in.payload.get("input", "")) or ""

    if req.mode == "openai_only":
        routed["openai"] = call_openai(user_text)
    elif req.mode == "manus_only":
        routed["manus"] = call_manus(env_in.model_dump(by_alias=True))
    elif req.mode == "openai_then_manus":
        o = call_openai(user_text)
        routed["openai"] = o
        manus_payload = {
            "envelope": env_in.model_dump(by_alias=True),
            "openai_result": o
        }
        routed["manus"] = call_manus(manus_payload)
    else:
        raise HTTPException(status_code=400, detail="Unknown mode")

    response_type = "response"
    if any(not r.get("ok", False) for r in routed.values()):
        response_type = "error"

    out_env = Envelope(
        **{
            "from": "bridge",
            "to": env_in.from_,
            "type": response_type,
            "threadId": env_in.threadId,
            "payload": {"routed": routed},
        }
    )

    store_event({
        "kind": "bridge_run_out",
        "messageId": out_env.messageId,
        "threadId": out_env.threadId,
        "mode": req.mode,
        "response_type": response_type,
    })

    return RunResponse(ok=True, envelope=out_env, routed=routed)




def extract_basic_fields(text: str) -> Dict[str, Any]:
    fields: Dict[str, Any] = {
        "document_number": None,
        "invoice_number": None,
        "waybill_number": None,
        "date": None,
        "total_amount": None,
        "vat_amount": None,
        "currency": None,
    }

    text_norm = text.replace("₾", " ₾ ")

    patterns_invoice = [
        r'(?i)\binvoice\s*(?:no|number|#|n)?\s*[:#]?\s*([A-Z0-9.\-\/]+)',
        r'(?i)ინვოის(?:ი)?\s*(?:no|number|#|n)?\s*[:#]?\s*([A-Z0-9.\-\/]+)',
        r'(?i)ანგარიშ(?:ი|[\-\s]*ფაქტურა)?\s*(?:no|number|#|n)?\s*[:#]?\s*([A-Z0-9.\-\/]+)',
    ]

    patterns_waybill = [
        r'(?im)^ელ[\-\s]*([0-9]{6,})\s*$',
        r'(?is)სასაქონლო\s+ზედნადები\s*#\s*[\r\n]+\s*ელ[\-\s]*([0-9]{6,})',
    ]

    patterns_date = [
        r'(?i)\b(\d{4}-\d{2}-\d{2})\b',
        r'(?i)\b(\d{2}[./-]\d{2}[./-]\d{4})\b',
    ]

    patterns_total = [
        r'(?i)\bgrand total\b\s*[:=]?\s*([0-9]+(?:[.,][0-9]{2,4})?)',
        r'(?i)\btotal\b\s*[:=]?\s*([0-9]+(?:[.,][0-9]{2,4})?)',
        r'(?i)\bსულ\b\s*[:=]?\s*([0-9]+(?:[.,][0-9]{2,4})?)',
        r'(?i)\b([0-9]+(?:[.,][0-9]{2,4})?)\s*(?:GEL|ლარი)\b',
        r'(?i)\b([0-9]+(?:[.,][0-9]{2,4})?)\s*₾',
        r'(?is)([0-9]+(?:[.,][0-9]{2,4})?)\s*-\s*[^\n]{0,120}\n\s*მიწოდებული საქონლის მთლიანი თანხა',
    ]

    patterns_vat = [
        r'(?i)\bvat\b\s*[:=]?\s*([0-9]+(?:[.,][0-9]{2,4})?)',
        r'(?i)\bდღგ(?:-?ს)?(?:\s*თანხა)?\b\s*[:=]?\s*([0-9]+(?:[.,][0-9]{2,4})?)',
    ]

    patterns_currency = [
        r'(?i)\b(GEL|USD|EUR)\b',
        r'(?i)\b(ლარი)\b',
        r'(₾)',
    ]

    for p in patterns_invoice:
        m = re.search(p, text_norm)
        if m:
            fields["invoice_number"] = m.group(1).strip()
            fields["document_number"] = fields["invoice_number"]
            break

    for p in patterns_waybill:
        m = re.search(p, text_norm)
        if m:
            fields["waybill_number"] = m.group(1).strip()
            if not fields["document_number"]:
                fields["document_number"] = fields["waybill_number"]
            break

    for p in patterns_date:
        m = re.search(p, text_norm)
        if m:
            fields["date"] = m.group(1).strip()
            break

    for p in patterns_total:
        m = re.search(p, text_norm)
        if m:
            fields["total_amount"] = m.group(1).replace(",", ".").strip()
            break

    for p in patterns_vat:
        m = re.search(p, text_norm)
        if m:
            fields["vat_amount"] = m.group(1).replace(",", ".").strip()
            break

    for p in patterns_currency:
        m = re.search(p, text_norm)
        if m:
            cur = m.group(1).strip()
            if cur in ("ლარი", "₾"):
                fields["currency"] = "GEL"
            else:
                fields["currency"] = cur.upper()
            break

    return fields

def extract_text_from_pdf_bytes(data: bytes) -> str:
    try:
        parts = []
        with fitz.open(stream=data, filetype="pdf") as doc:
            for i, page in enumerate(doc):
                txt = page.get_text("text") or ""
                if txt.strip():
                    parts.append(f"\n\n--- PAGE {i+1} ---\n{txt}")

        text = "".join(parts).strip()
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF read failed: {e}")


@app.post("/bridge/pdf/analyze", response_model=Dict[str, Any])
async def bridge_pdf_analyze(
    file: UploadFile = File(...),
    threadId: Optional[str] = Form(None)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    raw = await file.read()
    text = extract_text_from_pdf_bytes(raw)

    if not text.strip():
        raise HTTPException(status_code=400, detail="No extractable text found in PDF")

    lowered = text.lower()
    doc_type = "unknown"

    invoice_hits = 0
    if "invoice" in lowered or "ინვოის" in lowered:
        invoice_hits += 1
    if "invoice #" in lowered or "invoice no" in lowered or "invoice number" in lowered:
        invoice_hits += 1
    if "total" in lowered or "subtotal" in lowered or "vat" in lowered:
        invoice_hits += 1

    waybill_hits = 0
    if "waybill" in lowered or "ზედნადებ" in lowered:
        waybill_hits += 1
    if "sender" in lowered or "receiver" in lowered or "transport" in lowered:
        waybill_hits += 1

    if invoice_hits >= 3 and invoice_hits > waybill_hits:
        doc_type = "invoice"
    elif waybill_hits >= 2 and waybill_hits > invoice_hits:
        doc_type = "waybill"

    fields = extract_basic_fields(text)

    invoice_score = 0
    waybill_score = 0

    lowered = text.lower()

    if "invoice" in lowered or "ინვოის" in lowered or "ანგარიშ" in lowered:
        invoice_score += 2
    if fields.get("invoice_number"):
        invoice_score += 1
    if "tbcge" in lowered or "invoice n" in lowered or "ინვოისი" in lowered:
        invoice_score += 1

    if "waybill" in lowered or "ზედნადებ" in lowered:
        waybill_score += 2
    if "მიმღები" in lowered or "გამგზავნი" in lowered or "საქონლის" in lowered:
        waybill_score += 1
    if "qty" in lowered or "რაოდენობა" in lowered:
        waybill_score += 1

    if doc_type == "unknown":
        if invoice_score >= 2 and invoice_score > waybill_score:
            doc_type = "invoice"
        elif waybill_score >= 2 and waybill_score > invoice_score:
            doc_type = "waybill"
    if doc_type == "invoice":
        if fields.get("invoice_number"):
            fields["document_number"] = fields["invoice_number"]
        fields["waybill_number"] = None

    elif doc_type == "waybill":
        if fields.get("waybill_number"):
            fields["document_number"] = fields["waybill_number"]
        fields["invoice_number"] = None

    validation = {
        "has_text": bool(text.strip()),
        "chars": len(text),
        "doc_type": doc_type,
    }

    if doc_type == "invoice":
        if fields.get("invoice_number"):
            fields["document_number"] = fields["invoice_number"]
        fields["waybill_number"] = None
    elif doc_type == "waybill":
        if fields.get("waybill_number"):
            fields["document_number"] = fields["waybill_number"]
        fields["invoice_number"] = None

    return {
        "ok": True,
        "type": "pdf_analysis",
        "threadId": threadId or "",
        "filename": file.filename,
        "doc_type": doc_type,
        "fields": fields,
        "validation": validation,
        "preview": text[:1500],
    }

@app.post("/webhook/charjibit", response_model=RunResponse)
def webhook_charjibit(payload: Dict[str, Any]):
    dedup_key = get_stable_dedup_key(payload)
    
    if is_duplicate(dedup_key):
        store_event({
            "kind": "charjibit_webhook_duplicate",
            "dedup_key": dedup_key,
            "action": "ignored",
        })
        return RunResponse(
            ok=False,
            envelope=Envelope(
                **{
                    "from": "bridge",
                    "to": "charjibit",
                    "type": "error",
                    "payload": {"error": "duplicate_message", "dedup_key": dedup_key},
                }
            ),
            routed={"action": "duplicate"},
        )

    mark_processed(dedup_key)

    env = Envelope(
        **{
            "messageId": dedup_key,
            "from": "charjibit",
            "to": "bridge",
            "type": "event",
            "payload": payload,
        }
    )

    store_event({
        "kind": "charjibit_webhook",
        "messageId": env.messageId,
        "threadId": env.threadId,
        "event_type": payload.get("event_type", "unknown"),
        "dedup_key": dedup_key,
    })

    out_env = Envelope(
        **{
            "from": "bridge",
            "to": "charjibit",
            "type": "response",
            "threadId": env.threadId,
            "payload": {
                "received": True,
                "messageId": env.messageId,
                "status": "ingested",
            },
        }
    )

    return RunResponse(ok=True, envelope=out_env, routed={"action": "charjibit_event_ingested"})


@app.post("/webhook/manus", response_model=RunResponse)
def webhook_manus(payload: Dict[str, Any]):
    dedup_key = get_stable_dedup_key(payload)
    
    if is_duplicate(dedup_key):
        store_event({
            "kind": "manus_webhook_duplicate",
            "dedup_key": dedup_key,
            "action": "ignored",
        })
        return RunResponse(
            ok=False,
            envelope=Envelope(
                **{
                    "from": "bridge",
                    "to": "manus",
                    "type": "error",
                    "payload": {"error": "duplicate_message", "dedup_key": dedup_key},
                }
            ),
            routed={"action": "duplicate"},
        )

    mark_processed(dedup_key)

    env = Envelope(
        **{
            "messageId": dedup_key,
            "from": "manus",
            "to": "bridge",
            "type": "event",
            "payload": payload,
        }
    )

    store_event({
        "kind": "manus_webhook",
        "messageId": env.messageId,
        "threadId": env.threadId,
        "event_type": payload.get("event_type", "unknown"),
        "dedup_key": dedup_key,
    })

    out_env = Envelope(
        **{
            "from": "bridge",
            "to": "manus",
            "type": "response",
            "threadId": env.threadId,
            "payload": {
                "received": True,
                "messageId": env.messageId,
                "status": "ingested",
            },
        }
    )

    return RunResponse(ok=True, envelope=out_env, routed={"action": "manus_event_ingested"})


@app.get("/debug/log")
def debug_log(limit: int = 50):
    return {
        "count": len(IN_MEMORY_LOG),
        "items": IN_MEMORY_LOG[-limit:],
    }


@app.on_event("startup")
async def startup_event():
    store_event({
        "kind": "startup",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ============================================================
# PHASE B: VALIDATION ENGINE
# ============================================================

class ValidationIssue(BaseModel):
    """Single validation issue"""
    rule: str
    severity: Literal["error", "warning", "info"]
    message: str
    field: Optional[str] = None
    proposed_fix: Optional[str] = None


class ValidationResult(BaseModel):
    """Validation result for a transaction"""
    ok: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    can_post: bool
    proposed_fixes: Dict[str, Any] = Field(default_factory=dict)


def validate_debit_credit(transaction: Dict[str, Any]) -> list[ValidationIssue]:
    """Debit must equal Credit"""
    issues = []
    debit = transaction.get("debit", 0)
    credit = transaction.get("credit", 0)
    
    if abs(debit - credit) > 0.01:
        issues.append(ValidationIssue(
            rule="debit_credit_mismatch",
            severity="error",
            message=f"Debit ({debit}) != Credit ({credit})",
            field="debit/credit",
            proposed_fix=f"Adjust credit to {debit}"
        ))
    
    return issues


def validate_vat(transaction: Dict[str, Any]) -> list[ValidationIssue]:
    """VAT must be 0%, 18%, or 20%"""
    issues = []
    vat_rate = transaction.get("vat_rate", 0)
    allowed_rates = [0, 18, 20]
    
    if vat_rate not in allowed_rates:
        issues.append(ValidationIssue(
            rule="invalid_vat_rate",
            severity="error",
            message=f"VAT rate {vat_rate}% not allowed. Use: {allowed_rates}",
            field="vat_rate",
            proposed_fix=f"Change to 18% or 20%"
        ))
    
    return issues


def validate_period_lock(transaction: Dict[str, Any], locked_periods: list[str]) -> list[ValidationIssue]:
    """Period must not be locked"""
    issues = []
    period = transaction.get("period")
    
    if period in locked_periods:
        issues.append(ValidationIssue(
            rule="period_locked",
            severity="error",
            message=f"Period {period} is locked. Contact accountant.",
            field="period",
            proposed_fix=f"Use a different period or unlock {period}"
        ))
    
    return issues


def validate_no_duplicate(transaction: Dict[str, Any], existing_docs: list[str]) -> list[ValidationIssue]:
    """Document ID must be unique"""
    issues = []
    doc_id = transaction.get("doc_id")
    
    if doc_id in existing_docs:
        issues.append(ValidationIssue(
            rule="duplicate_document",
            severity="error",
            message=f"Document {doc_id} already exists",
            field="doc_id",
            proposed_fix=f"Use a new document ID"
        ))
    
    return issues


def validate_transaction(
    transaction: Dict[str, Any],
    locked_periods: list[str] = None,
    existing_docs: list[str] = None
) -> ValidationResult:
    """Validate a single transaction"""
    
    if locked_periods is None:
        locked_periods = []
    if existing_docs is None:
        existing_docs = []
    
    all_issues = []
    
    all_issues.extend(validate_debit_credit(transaction))
    all_issues.extend(validate_vat(transaction))
    all_issues.extend(validate_period_lock(transaction, locked_periods))
    all_issues.extend(validate_no_duplicate(transaction, existing_docs))
    
    errors = [i for i in all_issues if i.severity == "error"]
    can_post = len(errors) == 0
    
    proposed_fixes = {}
    for issue in all_issues:
        if issue.proposed_fix:
            proposed_fixes[issue.rule] = issue.proposed_fix
    
    return ValidationResult(
        ok=can_post,
        issues=all_issues,
        can_post=can_post,
        proposed_fixes=proposed_fixes
    )


@app.post("/bridge/validate", response_model=Dict[str, Any])
def validate_bridge(payload: Dict[str, Any]):
    """Validate a transaction against deterministic rules"""
    
    transaction = payload.get("transaction", {})
    locked_periods = payload.get("locked_periods", [])
    existing_docs = payload.get("existing_docs", [])
    
    result = validate_transaction(transaction, locked_periods, existing_docs)
    
    store_event({
        "kind": "validation_run",
        "transaction_id": transaction.get("doc_id"),
        "can_post": result.can_post,
        "issue_count": len(result.issues),
    })
    
    return {
        "ok": result.ok,
        "can_post": result.can_post,
        "issues": [issue.model_dump() for issue in result.issues],
        "proposed_fixes": result.proposed_fixes,
    }


# ============================================================
# ============================================================
# PHASE C: ISSUES QUEUE (Approval Workflow)
# ============================================================

class IssueItem(BaseModel):
    issue_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    transaction_id: str
    threadId: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    issues: list[ValidationIssue]
    proposed_fixes: Dict[str, Any]
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_at: Optional[str] = None
    accountant_comment: Optional[str] = None


ISSUES_QUEUE: list[IssueItem] = []


@app.get("/bridge/issues/queue", response_model=Dict[str, Any])
def get_issues_queue():
    pending = [i for i in ISSUES_QUEUE if i.status == "pending"]
    return {
        "count": len(pending),
        "items": [item.model_dump() for item in pending],
    }


@app.post("/bridge/issues/approve", response_model=Dict[str, Any])
def approve_issue(payload: Dict[str, Any]):
    issue_id = payload.get("issue_id")
    comment = payload.get("comment", "")

    issue = next((i for i in ISSUES_QUEUE if i.issue_id == issue_id), None)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    if issue.status != "pending":
        raise HTTPException(status_code=400, detail=f"Issue already {issue.status}")

    issue.status = "approved"
    issue.approved_at = datetime.now(timezone.utc).isoformat()
    issue.accountant_comment = comment

    store_event({
        "kind": "issue_approved",
        "issue_id": issue_id,
        "transaction_id": issue.transaction_id,
        "accountant_comment": comment,
    })

    return {
        "ok": True,
        "issue_id": issue_id,
        "status": "approved",
        "message": f"Issue {issue_id} approved by accountant",
    }


@app.post("/bridge/issues/reject", response_model=Dict[str, Any])
def reject_issue(payload: Dict[str, Any]):
    issue_id = payload.get("issue_id")
    comment = payload.get("comment", "")

    issue = next((i for i in ISSUES_QUEUE if i.issue_id == issue_id), None)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    if issue.status != "pending":
        raise HTTPException(status_code=400, detail=f"Issue already {issue.status}")

    issue.status = "rejected"
    issue.accountant_comment = comment

    store_event({
        "kind": "issue_rejected",
        "issue_id": issue_id,
        "transaction_id": issue.transaction_id,
        "accountant_comment": comment,
    })

    return {
        "ok": True,
        "issue_id": issue_id,
        "status": "rejected",
        "message": f"Issue {issue_id} rejected by accountant",
    }

# PHASE: BRIDGE HUB E2E (Charjibit â†’ Validation â†’ Queue â†’ Approval â†’ OpenAI/Manus)
# ============================================================

@app.post("/bridge/e2e", response_model=Dict[str, Any])
def bridge_e2e(payload: Dict[str, Any]):
    """
    End-to-end flow:
    1. Charjibit event â†’ Envelope
    2. Validate transaction
    3. If issues â†’ Queue for approval
    4. If approved â†’ Route to OpenAI + Manus
    5. Return results
    """
    
    # Step 1: Charjibit event â†’ Envelope
    charjibit_event = payload.get("charjibit_event", {})
    dedup_key = get_stable_dedup_key(charjibit_event)
    
    if is_duplicate(dedup_key):
        return {
            "ok": False,
            "error": "duplicate_message",
            "dedup_key": dedup_key,
        }
    
    mark_processed(dedup_key)
    
    envelope = Envelope(
        messageId=dedup_key,
        from_="charjibit",
        to="bridge",
        type="event",
        payload=charjibit_event,
    )
    
    store_event({
        "kind": "e2e_start",
        "messageId": envelope.messageId,
        "threadId": envelope.threadId,
        "charjibit_event_type": charjibit_event.get("event_type"),
    })
    
    # Step 2: Validate transaction
    transaction = charjibit_event.get("transaction", {})
    locked_periods = payload.get("locked_periods", [])
    existing_docs = payload.get("existing_docs", [])
    
    validation_result = validate_transaction(transaction, locked_periods, existing_docs)
    
    store_event({
        "kind": "e2e_validation",
        "messageId": envelope.messageId,
        "can_post": validation_result.can_post,
        "issue_count": len(validation_result.issues),
    })
    
    # Step 3: If issues â†’ Queue for approval
    if not validation_result.can_post:
        issue_item = IssueItem(
            transaction_id=transaction.get("doc_id", "unknown"),
            threadId=envelope.threadId,
            issues=validation_result.issues,
            proposed_fixes=validation_result.proposed_fixes,
        )
        ISSUES_QUEUE.append(issue_item)
        
        store_event({
            "kind": "e2e_queued_for_approval",
            "messageId": envelope.messageId,
            "issue_id": issue_item.issue_id,
        })
        
        return {
            "ok": False,
            "status": "queued_for_approval",
            "issue_id": issue_item.issue_id,
            "issues": [issue.model_dump() for issue in validation_result.issues],
            "proposed_fixes": validation_result.proposed_fixes,
            "message": "Transaction has validation issues. Waiting for accountant approval.",
        }
    
    # Step 4: If approved â†’ Route to OpenAI + Manus
    routed = {}
    
    # OpenAI
    user_text = charjibit_event.get("description", "") or str(charjibit_event)
    routed["openai"] = call_openai(user_text)
    
    # Manus
    routed["manus"] = call_manus(envelope.model_dump(by_alias=True))
    
    store_event({
        "kind": "e2e_routed",
        "messageId": envelope.messageId,
        "openai_ok": routed["openai"].get("ok"),
        "manus_ok": routed["manus"].get("ok"),
    })
    
    # Step 5: Return results
    response_envelope = Envelope(
        from_="bridge",
        to="charjibit",
        type="response",
        threadId=envelope.threadId,
        payload={
            "original_message_id": envelope.messageId,
            "validation_ok": True,
            "routed": routed,
        },
    )
    
    store_event({
        "kind": "e2e_complete",
        "messageId": response_envelope.messageId,
        "threadId": response_envelope.threadId,
    })
    
    return {
        "ok": True,
        "status": "complete",
        "envelope": response_envelope.model_dump(by_alias=True),
        "routed": routed,
    }


# ============================================================
# CHARJIBIT API INTEGRATION
# ============================================================

class CharjibitConfig(BaseModel):
    api_url: str = "https://api.charjibit.ge"
    api_key: Optional[str] = None
    webhook_url: Optional[str] = None


class CharjibitTransaction(BaseModel ):
    id: str
    date: str
    amount: float
    currency: str = "GEL"
    description: str
    account_from: str
    account_to: str
    status: str = "pending"


charjibit_config = CharjibitConfig(
    api_url=os.getenv("CHARJIBIT_API_URL", "https://api.charjibit.ge" ),
    api_key=os.getenv("CHARJIBIT_API_KEY"),
    webhook_url=os.getenv("CHARJIBIT_WEBHOOK_URL"),
)


def charjibit_get_transactions(start_date: str, end_date: str) -> list[CharjibitTransaction]:
    """Fetch transactions from Charjibit API"""
    if not charjibit_config.api_key:
        return []
    
    try:
        response = requests.get(
            f"{charjibit_config.api_url}/transactions",
            headers={"Authorization": f"Bearer {charjibit_config.api_key}"},
            params={"start_date": start_date, "end_date": end_date},
            timeout=10,
        )
        response.raise_for_status()
        
        transactions = []
        for item in response.json().get("data", []):
            transactions.append(CharjibitTransaction(**item))
        
        return transactions
    except Exception as e:
        store_event({
            "kind": "charjibit_fetch_error",
            "error": str(e),
        })
        return []


def charjibit_post_transaction(transaction: Dict[str, Any]) -> Dict[str, Any]:
    """Post transaction result back to Charjibit"""
    if not charjibit_config.api_key:
        return {"ok": False, "error": "CHARJIBIT_API_KEY not set"}
    
    try:
        response = requests.post(
            f"{charjibit_config.api_url}/transactions/{transaction.get('id')}/result",
            headers={"Authorization": f"Bearer {charjibit_config.api_key}"},
            json={"status": "processed", "result": transaction},
            timeout=10,
        )
        response.raise_for_status()
        
        store_event({
            "kind": "charjibit_post_success",
            "transaction_id": transaction.get("id"),
        })
        
        return {"ok": True, "response": response.json()}
    except Exception as e:
        store_event({
            "kind": "charjibit_post_error",
            "transaction_id": transaction.get("id"),
            "error": str(e),
        })
        return {"ok": False, "error": str(e)}


@app.get("/charjibit/transactions")
def get_charjibit_transactions(start_date: str, end_date: str):
    """Fetch transactions from Charjibit"""
    transactions = charjibit_get_transactions(start_date, end_date)
    
    store_event({
        "kind": "charjibit_fetch",
        "count": len(transactions),
        "start_date": start_date,
        "end_date": end_date,
    })
    
    return {
        "ok": True,
        "count": len(transactions),
        "transactions": [t.model_dump() for t in transactions],
    }


@app.post("/charjibit/sync")
def sync_charjibit_to_bridge(payload: Dict[str, Any]):
    """Sync Charjibit transactions through Bridge Hub"""
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    
    transactions = charjibit_get_transactions(start_date, end_date)
    
    results = []
    for txn in transactions:
        # Route through Bridge Hub E2E
        result = bridge_e2e({
            "charjibit_event": {
                "event_id": txn.id,
                "event_type": "transaction_sync",
                "description": txn.description,
                "transaction": txn.model_dump(),
            }
        })
        results.append(result)
    
    store_event({
        "kind": "charjibit_sync",
        "count": len(transactions),
        "results_count": len(results),
    })
    
    return {
        "ok": True,
        "count": len(transactions),
        "results": results,
    }


# ============================================================
# MANUS WEBHOOK INTEGRATION
# ============================================================

class ManusConfig(BaseModel):
    webhook_url: Optional[str] = None
    api_key: Optional[str] = None


manus_config = ManusConfig(
    webhook_url=os.getenv("MANUS_WEBHOOK_URL"),
    api_key=os.getenv("MANUS_API_KEY"),
)


def manus_send_webhook(event: Dict[str, Any]) -> Dict[str, Any]:
    """Send event to Manus webhook"""
    if not manus_config.webhook_url:
        return {"ok": False, "error": "MANUS_WEBHOOK_URL not set", "mode": "mock"}
    
    try:
        response = requests.post(
            manus_config.webhook_url,
            json=event,
            headers={"Authorization": f"Bearer {manus_config.api_key}"} if manus_config.api_key else {},
            timeout=10,
        )
        response.raise_for_status()
        
        store_event({
            "kind": "manus_webhook_sent",
            "event_type": event.get("type"),
            "status_code": response.status_code,
        })
        
        return {"ok": True, "response": response.json()}
    except Exception as e:
        store_event({
            "kind": "manus_webhook_error",
            "event_type": event.get("type"),
            "error": str(e),
        })
        return {"ok": False, "error": str(e)}


@app.post("/manus/send-event")
def send_to_manus(payload: Dict[str, Any]):
    """Send event to Manus"""
    result = manus_send_webhook(payload)
    return result


@app.post("/manus/receive-feedback")
def receive_manus_feedback(payload: Dict[str, Any]):
    """Receive feedback from Manus"""
    feedback = payload.get("feedback", {})
    
    store_event({
        "kind": "manus_feedback_received",
        "feedback_type": feedback.get("type"),
        "message_id": feedback.get("message_id"),
    })
    
    return {
        "ok": True,
        "message": "Feedback received and logged",
    }


# ============================================================
# CLOUD STORAGE INTEGRATION (Google Cloud Storage)
# ============================================================

class CloudStorageConfig(BaseModel):
    bucket_name: Optional[str] = None
    project_id: Optional[str] = None


cloud_storage_config = CloudStorageConfig(
    bucket_name=os.getenv("GCS_BUCKET_NAME"),
    project_id=os.getenv("GCP_PROJECT_ID"),
)


def cloud_storage_save_transaction(transaction: Dict[str, Any], folder: str = "transactions") -> Dict[str, Any]:
    """Save transaction to Cloud Storage"""
    if not cloud_storage_config.bucket_name:
        return {"ok": False, "error": "GCS_BUCKET_NAME not set", "mode": "mock"}
    
    try:
        from google.cloud import storage
        
        client = storage.Client(project=cloud_storage_config.project_id)
        bucket = client.bucket(cloud_storage_config.bucket_name)
        
        filename = f"{folder}/{transaction.get('doc_id', 'unknown')}-{datetime.now(timezone.utc).isoformat()}.json"
        blob = bucket.blob(filename)
        blob.upload_from_string(json.dumps(transaction, indent=2))
        
        store_event({
            "kind": "cloud_storage_save",
            "filename": filename,
            "transaction_id": transaction.get("doc_id"),
        })
        
        return {"ok": True, "filename": filename, "url": f"gs://{cloud_storage_config.bucket_name}/{filename}"}
    except Exception as e:
        store_event({
            "kind": "cloud_storage_error",
            "error": str(e),
        })
        return {"ok": False, "error": str(e)}


@app.post("/cloud/save-transaction")
def save_to_cloud(payload: Dict[str, Any]):
    """Save transaction to Cloud Storage"""
    transaction = payload.get("transaction", {})
    folder = payload.get("folder", "transactions")
    
    result = cloud_storage_save_transaction(transaction, folder)
    return result


@app.get("/cloud/list-transactions")
def list_cloud_transactions(folder: str = "transactions"):
    """List transactions in Cloud Storage"""
    if not cloud_storage_config.bucket_name:
        return {"ok": False, "error": "GCS_BUCKET_NAME not set", "mode": "mock", "items": []}
    
    try:
        from google.cloud import storage
        
        client = storage.Client(project=cloud_storage_config.project_id)
        bucket = client.bucket(cloud_storage_config.bucket_name)
        
        blobs = bucket.list_blobs(prefix=f"{folder}/")
        items = [{"name": blob.name, "size": blob.size, "updated": blob.updated.isoformat()} for blob in blobs]
        
        store_event({
            "kind": "cloud_storage_list",
            "folder": folder,
            "count": len(items),
        })
        
        return {"ok": True, "folder": folder, "count": len(items), "items": items}
    except Exception as e:
        store_event({
            "kind": "cloud_storage_list_error",
            "error": str(e),
        })
        return {"ok": False, "error": str(e)}










