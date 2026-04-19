"""
Bridge Hub — Direct Claude Chat
/api/claude/chat  →  Claude Sonnet (Anthropic API)
Supports text + file upload (PDF/DOCX/CSV/XLSX)
"""
import os
import io
import logging
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/claude", tags=["Claude Chat"])

SYSTEM_PROMPT = """შენ ხარ Bridge Hub AI — ქართული ფინანსური OS-ის ასისტენტი.
შენ ეხმარები ბუღალტრებს, ფინანსურ მენეჯერებს და მეწარმეებს.

შენი ექსპერტიზა:
- ქართული საგადასახადო კოდექსი (დღგ 18%, საშემოსავლო 20%, მოგების 15%, სოციალური 2%)
- IFRS/GAAP ბუღალტრული პრინციპები
- ჟურნალის ჩანაწერები და ანგარიშთა გეგმა (COA)
- ხელფასი, დივიდენდი, ამორტიზაცია
- ფინანსური ანგარიშები (ბალანსი, მოგება-ზარალი, ფულის ნაკადი)
- ბანკის ამონაწერები და რეკონსილიაცია

გასცე სრული, ზუსტი, ქართულ ენაზე პასუხები.
თუ ფაილია მოწოდებული, გაანალიზე და კონკრეტული ინფორმაცია გასცე.
"""


def _read_file_text(filename: str, data: bytes) -> str:
    """Extract text from uploaded file."""
    fn = filename.lower()
    try:
        if fn.endswith(".pdf"):
            import fitz
            doc = fitz.open(stream=data, filetype="pdf")
            return "\n".join(doc[i].get_text() for i in range(min(len(doc), 20)))
        if fn.endswith(".docx"):
            import docx
            doc = docx.Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        if fn.endswith(".csv"):
            return data.decode("utf-8", errors="replace")[:8000]
        if fn.endswith((".xlsx", ".xls")):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
                lines = []
                for ws in wb.worksheets[:3]:
                    for row in ws.iter_rows(max_row=100, values_only=True):
                        lines.append("\t".join(str(c or "") for c in row))
                return "\n".join(lines)
            except Exception:
                return data.decode("utf-8", errors="replace")[:8000]
    except Exception as e:
        log.warning("file parse error %s: %s", filename, e)
    return f"[ფაილი: {filename} — ტექსტი ვერ წაიკითხა]"


@router.post("/chat")
async def claude_chat(
    message: str = Form(""),
    session_id: str = Form(None),
    history: str = Form("[]"),
    file: UploadFile = File(None),
):
    message = (message or "").strip()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return JSONResponse(status_code=503, content={"ok": False, "answer": "ANTHROPIC_API_KEY არ არის კონფიგურირებული."})

    try:
        import anthropic
        import json as _json

        client = anthropic.Anthropic(api_key=api_key)

        # Parse history: [{role, text}]
        try:
            hist = _json.loads(history) if history else []
        except Exception:
            hist = []

        # Build messages list
        messages = []
        for h in hist[-10:]:  # last 10 turns
            role = "user" if h.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": h.get("text", "")})

        # Build current user content
        content_parts = []

        if file:
            raw = await file.read()
            file_text = _read_file_text(file.filename, raw)
            content_parts.append({
                "type": "text",
                "text": f"ატვირთული ფაილი: {file.filename}\n\n{file_text[:12000]}"
            })

        user_text = message or ("გაანალიზე ეს ფაილი" if file else "გამარჯობა")
        content_parts.append({"type": "text", "text": user_text})

        messages.append({"role": "user", "content": content_parts})

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        answer = resp.content[0].text if resp.content else "პასუხი ვერ მივიღე."
        return {"ok": True, "answer": answer, "model": "claude-sonnet-4-6"}

    except Exception as e:
        log.error("claude_chat error: %s", e)
        return JSONResponse(status_code=500, content={"ok": False, "answer": f"შეცდომა: {e}"})
