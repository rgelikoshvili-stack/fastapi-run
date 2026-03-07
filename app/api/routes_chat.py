from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional
import psycopg2
import psycopg2.extras
from app.api.db import get_db

router = APIRouter(prefix="/chat", tags=["chat"])





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


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = "default"


@router.post("/message")
def send_message(payload: ChatMessageRequest):
    session_id = payload.session_id or "default"
    user_msg = payload.message.strip()

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    ensure_tables(cur)

    cur.execute(
        """
        INSERT INTO chat_sessions (session_id, title)
        VALUES (%s, %s)
        ON CONFLICT (session_id) DO NOTHING
        """,
        (session_id, user_msg[:50]),
    )

    cur.execute(
        """
        INSERT INTO chat_messages (session_id, role, content)
        VALUES (%s, 'user', %s)
        """,
        (session_id, user_msg),
    )
    conn.commit()

    reply = f"Bridge Hub AI: მიიღე შეტყობინება '{user_msg}'. სისტემა მუშაობს. (AI Sprint 56-ში)"

    cur.execute(
        """
        INSERT INTO chat_messages (session_id, role, content)
        VALUES (%s, 'assistant', %s)
        """,
        (session_id, reply),
    )
    conn.commit()

    cur.close()
    conn.close()

    return {
        "ok": True,
        "message": "Chat message processed",
        "data": {
            "session_id": session_id,
            "reply": reply,
        },
        "error": None,
    }


@router.get("/history/{session_id}")
def chat_history(session_id: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    ensure_tables(cur)
    conn.commit()

    cur.execute(
        """
        SELECT role, content, created_at
        FROM chat_messages
        WHERE session_id=%s
        ORDER BY created_at ASC
        """,
        (session_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()

    return {
        "ok": True,
        "message": "Chat history loaded",
        "data": {
            "session_id": session_id,
            "messages": rows,
        },
        "error": None,
    }


@router.get("/sessions")
def list_sessions():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    ensure_tables(cur)
    conn.commit()

    cur.execute("""
        SELECT
            s.session_id,
            s.title,
            s.created_at,
            COUNT(m.id) as message_count
        FROM chat_sessions s
        LEFT JOIN chat_messages m ON s.session_id = m.session_id
        GROUP BY s.session_id, s.title, s.created_at
        ORDER BY s.created_at DESC
        LIMIT 20
    """)
    rows = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()

    return {
        "ok": True,
        "message": "Chat sessions loaded",
        "data": {
            "sessions": rows,
        },
        "error": None,
    }


@router.delete("/session/{session_id}")
def delete_session(session_id: str):
    conn = get_db()
    cur = conn.cursor()

    ensure_tables(cur)

    cur.execute("DELETE FROM chat_messages WHERE session_id=%s", (session_id,))
    cur.execute("DELETE FROM chat_sessions WHERE session_id=%s", (session_id,))
    conn.commit()

    cur.close()
    conn.close()

    return {
        "ok": True,
        "message": f"Session {session_id} deleted",
        "data": {
            "session_id": session_id,
        },
        "error": None,
    }
