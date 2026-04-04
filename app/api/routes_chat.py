from fastapi import APIRouter, Request, File, UploadFile, Form
from typing import Optional
from app.api.response_utils import ok_response, error_response
from app.api.tenant_context import resolve_tenant_id
import os, anthropic, base64, json, psycopg2
from app.api.db import get_db

router = APIRouter(prefix="/chat", tags=["chat"])

# In-memory conversation history per session
_sessions: dict = {}

SYSTEM_PROMPT = """შენ ხარ Bridge Hub-ის AI ასისტენტი — ქართული AI საბუღალტრო სისტემა.

შენ შეგიძლია:
1. ბუღალტრული კითხვების პასუხი (VAT 18%, PAYG 2%, account codes)
2. CSV/Excel ფაილების ანალიზი — ტრანზაქციების კლასიფიკაცია
3. PDF ინვოისების parsing — draft-ების შექმნა
4. Balance.ge, 1C, ORIS, RS.GE ოპერაციების დახმარება
5. ფინანსური ანგარიშგება და ანალიზი
6. ანომალიების პოვნა ტრანზაქციებში

ქართული საბუღალტრო account codes:
7110=ხელფასი, 7130=კომუნალური, 7150=საბანკო კომისია,
7190=სხვა ხარჯი, 6100=შემოსავალი, 3100=გადასახადი,
1010=საბანკო ანგარიში, 3310=VAT output, 3330=VAT input

გვიპასუხე ქართულად, კონკრეტულად და სასარგებლოდ.
თუ ფაილი მოგცეს — გააანალიზე და კონკრეტული შედეგი მიეცი."""


def _get_db_context(tenant_id: str) -> str:
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM journal_drafts WHERE tenant_id=%s AND status IN ('drafted','pending_approval')", (tenant_id,))
        pending = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM journal_drafts WHERE tenant_id=%s AND status='approved'", (tenant_id,))
        approved = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM learning_patterns WHERE tenant_id=%s AND status='active'", (tenant_id,))
        patterns = cur.fetchone()[0]
        cur.close()
        conn.close()
        return f"\nDB სტატუსი: {pending} pending, {approved} approved, {patterns} active patterns"
    except:
        return ""


@router.post("/message")
async def send_message(
    request: Request,
    message: str = Form(...),
    session_id: str = Form("default"),
    file: Optional[UploadFile] = File(None)
):
    try:
        tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        if session_id not in _sessions:
            _sessions[session_id] = []

        history = _sessions[session_id]
        db_ctx = _get_db_context(tenant_id)
        system = SYSTEM_PROMPT + db_ctx + f"\nTenant: {tenant_id}"

        content = []

        if file:
            file_bytes = await file.read()
            fname = file.filename.lower()
            if fname.endswith(('.jpg','.jpeg','.png','.gif','.webp')):
                b64 = base64.standard_b64encode(file_bytes).decode()
                mt = file.content_type or "image/jpeg"
                content.append({"type":"image","source":{"type":"base64","media_type":mt,"data":b64}})
                content.append({"type":"text","text":f"{message}\n\n[ფაილი: {file.filename}]"})
            elif fname.endswith('.pdf'):
                b64 = base64.standard_b64encode(file_bytes).decode()
                content.append({"type":"document","source":{"type":"base64","media_type":"application/pdf","data":b64}})
                content.append({"type":"text","text":f"{message}\n\n[PDF: {file.filename}]"})
            else:
                text_content = file_bytes.decode("utf-8", errors="replace")[:8000]
                content.append({"type":"text","text":f"{message}\n\n[ფაილი: {file.filename}]\n```\n{text_content}\n```"})
        else:
            content.append({"type":"text","text":message})

        history.append({"role":"user","content":content})
        if len(history) > 20:
            history = history[-20:]

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=system,
            messages=history
        )
        reply = resp.content[0].text
        history.append({"role":"assistant","content":reply})
        _sessions[session_id] = history

        return ok_response("Chat response", {
            "reply": reply,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "tokens": resp.usage.input_tokens + resp.usage.output_tokens
        })
    except Exception as e:
        return error_response("Chat failed", "CHAT_ERROR", str(e))


@router.delete("/session/{session_id}")
def clear_session(session_id: str):
    _sessions.pop(session_id, None)
    return ok_response("Session cleared", {"session_id": session_id})


@router.get("/history")
def chat_history(session_id: str = "default"):
    return ok_response("Chat history", {
        "session_id": session_id,
        "messages": _sessions.get(session_id, [])
    })
