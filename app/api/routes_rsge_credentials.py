"""app/api/routes_rsge_credentials.py
Bridge Hub — Per-tenant RS.ge (Revenue Service) credentials.
Stores RS.ge portal username/password for future direct API posting.
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional

from app.api.tenant_context import resolve_tenant_id
from app.api.db import get_db

router = APIRouter(prefix="/rsge-credentials", tags=["rsge-credentials"])


class RsgeCredsPayload(BaseModel):
    username: str
    password: str
    taxpayer_inn: Optional[str] = ""


def _ensure_table():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tenant_rsge_credentials (
                id           SERIAL PRIMARY KEY,
                tenant_id    TEXT NOT NULL UNIQUE,
                username     TEXT NOT NULL,
                password     TEXT NOT NULL,
                taxpayer_inn TEXT DEFAULT '',
                updated_at   TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        conn.commit()
    finally:
        cur.close()
        conn.close()


@router.get("/status")
def get_status(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        _ensure_table()
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT username, taxpayer_inn FROM tenant_rsge_credentials WHERE tenant_id = %s",
            (tenant_id,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {"ok": True, "configured": True, "username": row[0], "taxpayer_inn": row[1]}
        return {"ok": True, "configured": False}
    except Exception as e:
        return {"ok": True, "configured": False, "error": str(e)}


@router.post("/save")
def save_creds(body: RsgeCredsPayload, request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if not body.username:
        return {"ok": False, "error": "username is required"}
    if not body.password:
        return {"ok": False, "error": "password is required"}
    try:
        _ensure_table()
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tenant_rsge_credentials (tenant_id, username, password, taxpayer_inn)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tenant_id) DO UPDATE
            SET username = EXCLUDED.username,
                password = EXCLUDED.password,
                taxpayer_inn = EXCLUDED.taxpayer_inn,
                updated_at = NOW()
            """,
            (tenant_id, body.username, body.password, body.taxpayer_inn or ""),
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"ok": True, "message": "RS.ge credentials saved"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/test")
def test_connection(request: Request):
    """Verify credentials are saved. Live portal validation coming soon."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT username, taxpayer_inn FROM tenant_rsge_credentials WHERE tenant_id = %s",
            (tenant_id,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {
                "ok": True,
                "message": f"Credentials saved for {row[0]}. Live RS.ge portal sync: coming soon.",
            }
        return {"ok": False, "error": "No credentials saved — please save first"}
    except Exception:
        return {"ok": False, "error": "Credentials not found"}
