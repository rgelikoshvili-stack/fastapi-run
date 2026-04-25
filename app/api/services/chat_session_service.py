"""
app/api/services/chat_session_service.py
Bridge Hub — Persistent Chat Session Storage

Replaces in-memory _chat_history dict with DB-backed storage.
Sessions survive Cloud Run restarts.

Table: chat_sessions
  session_id  TEXT  — client-generated UUID
  tenant_id   TEXT  — tenant isolation
  messages    JSONB — [{role, content}, ...]  (last N turns)
  updated_at  TIMESTAMPTZ
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import psycopg2.extras

from app.api.db import get_db

log = logging.getLogger(__name__)

MAX_TURNS = 20  # keep last 20 messages (10 turns)


def load_history(session_id: str, tenant_id: str) -> list[dict]:
    """Load conversation history from DB. Returns [] on any error."""
    if not session_id:
        return []
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT messages FROM chat_sessions WHERE session_id=%s AND tenant_id=%s",
            (session_id, tenant_id),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return []
        msgs = row["messages"]
        if isinstance(msgs, str):
            msgs = json.loads(msgs)
        return msgs if isinstance(msgs, list) else []
    except Exception as e:
        log.debug("load_history failed: %s", e)
        return []


def save_history(
    session_id: str,
    tenant_id: str,
    messages: list[dict],
    role: Optional[str] = None,
) -> None:
    """Upsert conversation history to DB. Trims to MAX_TURNS."""
    if not session_id:
        return
    try:
        trimmed = messages[-MAX_TURNS:]
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO chat_sessions (session_id, tenant_id, role, messages, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (session_id, tenant_id)
            DO UPDATE SET
                messages   = EXCLUDED.messages,
                role       = COALESCE(EXCLUDED.role, chat_sessions.role),
                updated_at = NOW()
            """,
            (session_id, tenant_id, role, json.dumps(trimmed, ensure_ascii=False)),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.debug("save_history failed: %s", e)


def clear_history(session_id: str, tenant_id: str) -> None:
    """Delete session history (user requests fresh start)."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM chat_sessions WHERE session_id=%s AND tenant_id=%s",
            (session_id, tenant_id),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.debug("clear_history failed: %s", e)


def get_session_summary(session_id: str, tenant_id: str) -> dict:
    """Return metadata about a session — for UI display."""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT session_id, tenant_id, role,
                   jsonb_array_length(messages) as message_count,
                   created_at, updated_at
            FROM chat_sessions
            WHERE session_id=%s AND tenant_id=%s
            """,
            (session_id, tenant_id),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"exists": False, "message_count": 0}
        return {
            "exists": True,
            "session_id": row["session_id"],
            "tenant_id": row["tenant_id"],
            "role": row["role"],
            "message_count": row["message_count"] or 0,
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }
    except Exception as e:
        log.debug("get_session_summary failed: %s", e)
        return {"exists": False, "message_count": 0, "error": str(e)}
