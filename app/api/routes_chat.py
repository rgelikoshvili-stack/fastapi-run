from fastapi import APIRouter, Request, File, UploadFile, Form
from typing import Optional
from app.api.response_utils import ok_response, error_response
from app.api.tenant_context import resolve_tenant_id
import os, anthropic, base64, json
from app.api.db import get_db

router = APIRouter(prefix="/chat", tags=["chat"])
_sessions: dict = {}

SYSTEM_PROMPT = """შენ ხარ Bridge Hub-ის სუპერ AI ასისტენტი — ქართული AI საბუღალტრო სისტემა.

შენ შეგიძლია:
1. PDF ინვოისების/ქვითრების წაკითხვა და გატარებების შექმნა
2. CSV/Excel საბანკო ამონაწერის ანალიზი და ავტო-კლასიფიკაცია
3. სურათებიდან (ქვითარი, ფაქტურა) ინფორმაციის ამოღება
4. ფინანსური ანომალიების გამოვლენა
5. VAT 18%, PAYG 2% გათვლები
6. ამ თვის/კვარტლის ხარჯების ანგარიში
7. ტრანზაქციების კლასიფიკაცია account code-ებით
8. Balance.ge, 1C, ORIS, RS.GE ოპერაციები
9. პატერნების პოვნა და learning
10. Multi-turn — კონტექსტი ახსოვს

ქართული account codes:
7110=ხელფასი, 7120=სოციალური, 7130=კომუნალური, 7140=software,
7150=საბანკო კომისია, 7160=სატრანსპორტო, 7170=მარკეტინგი,
7180=საოფისე, 7190=სხვა ხარჯი, 6100=შემოსავალი,
3100=გადასახადი, 3310=VAT output, 3330=VAT input,
1010=საბანკო ანგარიში, 1210=გადარიცხვა

CSV ანალიზისას:
- ყოველ სტრიქონს account code მიანიჭე
- ანომალიები მონიშნე
- VAT გამოყავი სადაც საჭიროა
- ჯამები და სტატისტიკა მოამზადე

გვიპასუხე ქართულად, კონკრეტულად. ფაილი თუ მოგცეს — სრული ანალიზი გაუკეთე."""


def _get_db_context(tenant_id: str) -> str:
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE status IN ('drafted','pending_approval')) as pending,
                COUNT(*) FILTER (WHERE status='approved') as approved,
                COUNT(*) FILTER (WHERE status='rejected') as rejected,
                COALESCE(SUM(amount) FILTER (WHERE status='approved'), 0) as total_approved
            FROM journal_drafts WHERE tenant_id=%s
        """, (tenant_id,))
        r = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM learning_patterns WHERE tenant_id=%s AND status='active'", (tenant_id,))
        patterns = cur.fetchone()[0]
        cur.execute("""
            SELECT account_code, COUNT(*) as cnt 
            FROM journal_drafts WHERE tenant_id=%s AND status='approved'
            GROUP BY account_code ORDER BY cnt DESC LIMIT 3
        """, (tenant_id,))
        top = cur.fetchall()
        cur.close()
        conn.close()
        top_str = ", ".join([f"{row[0]}({row[1]})" for row in top])
        return (f"\nDB: {r[0]} pending, {r[1]} approved, {r[2]} rejected"
                f"\nდამტკ. ჯამი: {round(float(r[3]),2)} GEL"
                f"\nActive patterns: {patterns}"
                f"\nTop accounts: {top_str}")
    except Exception as e:
        return f"\nDB: მიუწვდომელია ({e})"


async def _process_file(file: UploadFile) -> list:
    content = []
    file_bytes = await file.read()
    fname = file.filename.lower()
    
    if fname.endswith(('.jpg','.jpeg','.png','.gif','.webp')):
        b64 = base64.standard_b64encode(file_bytes).decode()
        mt = file.content_type or "image/jpeg"
        content.append({"type":"image","source":{"type":"base64","media_type":mt,"data":b64}})
    elif fname.endswith('.pdf'):
        b64 = base64.standard_b64encode(file_bytes).decode()
        content.append({"type":"document","source":{"type":"base64","media_type":"application/pdf","data":b64}})
    elif fname.endswith(('.xlsx','.xls')):
        try:
            import openpyxl
            from io import BytesIO
            wb = openpyxl.load_workbook(BytesIO(file_bytes))
            ws = wb.active
            rows = []
            for row in ws.iter_rows(values_only=True):
                if any(v is not None for v in row):
                    rows.append("\t".join([str(v) if v is not None else "" for v in row]))
            text = "\n".join(rows[:200])
            content.append({"type":"text","text":f"[Excel: {file.filename}]\n```\n{text}\n```"})
        except Exception:
            content.append({"type":"text","text":f"[Excel: {file.filename}] — ვერ გაიხსნა"})
    else:
        text = file_bytes.decode("utf-8", errors="replace")[:10000]
        content.append({"type":"text","text":f"[{file.filename}]\n```\n{text}\n```"})
    
    return content


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
        if file and file.filename:
            file_content = await _process_file(file)
            content.extend(file_content)
            content.append({"type":"text","text":f"{message}\n[ფაილი: {file.filename}]"})
        else:
            content.append({"type":"text","text":message})

        history.append({"role":"user","content":content})
        if len(history) > 30:
            history = history[-30:]

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
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
            "tokens": resp.usage.input_tokens + resp.usage.output_tokens,
            "has_file": bool(file and file.filename)
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
        "count": len(_sessions.get(session_id, [])),
        "messages": _sessions.get(session_id, [])
    })
