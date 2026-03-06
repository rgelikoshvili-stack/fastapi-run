from fastapi import APIRouter
import psycopg2, psycopg2.extras, os, json
from datetime import datetime
from openai import OpenAI

router = APIRouter(prefix="/chat", tags=["chat"])

def get_db():
    return psycopg2.connect(host="35.192.214.120", dbname="bridgehub", user="postgres", password="BridgeHub2026x")

def ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(100) UNIQUE,
            title VARCHAR(200),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(100),
            role VARCHAR(20),
            content TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

def get_system_context():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT COUNT(*) as total FROM pipeline_runs")
        total = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) as c FROM pipeline_runs WHERE status='APPROVED'")
        approved = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM pipeline_runs WHERE status='PENDING_APPROVAL'")
        pending = cur.fetchone()["c"]
        cur.execute("SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) as v FROM bank_transactions")
        inflow = float(cur.fetchone()["v"])
        cur.execute("SELECT COALESCE(SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END),0) as v FROM bank_transactions")
        outflow = float(cur.fetchone()["v"])
        cur.execute("SELECT COUNT(*) as c FROM bank_transactions")
        txs = cur.fetchone()["c"]
        cur.close(); conn.close()
        return f"""შენ ხარ Bridge Hub-ის AI ასისტენტი — ქართული AI Financial OS.

მიმდინარე სისტემის მდგომარეობა:
- სულ დოკუმენტები: {total} (დამტკიცებული: {approved}, მოლოდინში: {pending})
- საბანკო ტრანზაქციები: {txs}
- შემოსავალი: {round(inflow,2)} GEL | გასავალი: {round(outflow,2)} GEL | Net: {round(inflow-outflow,2)} GEL

Bridge Hub-ის მოდულები:
- Pipeline: PDF დოკუმენტების AI დამუშავება
- COA: ქართული საბუღალტრო გეგმა (35 ანგარიში)
- Supervisor: Multi-Agent routing
- Audit Engine: დუბლიკატები, ანომალიები
- Bank CSV: TBC/BOG/RUS პარსინგი
- Reconciliation: Bank-Ledger შეჯერება
- Finance KPI: Cashflow ანალიზი
- Strategy/CFO: AI რეკომენდაციები
- FP&A: Budget vs Actual, Forecast
- Reports: Monthly/Annual
- Learning Loop: AI სწავლება
- Notifications: Webhooks
- Multi-tenant: User Roles

უპასუხე ქართულად, მოკლედ და კონკრეტულად."""
    except:
        return "შენ ხარ Bridge Hub AI ასისტენტი. უპასუხე ქართულად."

@router.post("/message")
def send_message(payload: dict):
    session_id = payload.get("session_id", "default")
    user_msg = payload.get("message", "")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    cur.execute("INSERT INTO chat_sessions (session_id, title) VALUES (%s,%s) ON CONFLICT (session_id) DO NOTHING",
        (session_id, user_msg[:50]))
    cur.execute("INSERT INTO chat_messages (session_id, role, content) VALUES (%s,'user',%s)",
        (session_id, user_msg))
    conn.commit()
    cur.execute("SELECT role, content FROM chat_messages WHERE session_id=%s ORDER BY created_at DESC LIMIT 10",
        (session_id,))
    history = list(reversed(cur.fetchall()))
    messages = [{"role": r["role"], "content": r["content"]} for r in history]
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": get_system_context()}] + messages,
        max_tokens=500
    )
    reply = response.choices[0].message.content
    cur.execute("INSERT INTO chat_messages (session_id, role, content) VALUES (%s,'assistant',%s)",
        (session_id, reply))
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "session_id": session_id, "reply": reply}

@router.get("/history/{session_id}")
def chat_history(session_id: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("SELECT role, content, created_at FROM chat_messages WHERE session_id=%s ORDER BY created_at ASC",
        (session_id,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "session_id": session_id, "messages": rows}

@router.get("/sessions")
def list_sessions():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("""SELECT s.session_id, s.title, s.created_at, COUNT(m.id) as message_count
        FROM chat_sessions s LEFT JOIN chat_messages m ON s.session_id=m.session_id
        GROUP BY s.session_id, s.title, s.created_at ORDER BY s.created_at DESC LIMIT 20""")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "sessions": rows}

@router.delete("/session/{session_id}")
def delete_session(session_id: str):
    conn = get_db()
    cur = conn.cursor()
    ensure_tables(cur)
    cur.execute("DELETE FROM chat_messages WHERE session_id=%s", (session_id,))
    cur.execute("DELETE FROM chat_sessions WHERE session_id=%s", (session_id,))
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "message": f"Session {session_id} deleted"}