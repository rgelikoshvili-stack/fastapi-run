from fastapi import APIRouter, Header
from pydantic import BaseModel
from typing import Optional
import psycopg2.extras
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/tenants", tags=["tenants"])

class TenantCreate(BaseModel):
    name: str
    code: str
    api_key: Optional[str] = None

def get_tenant_by_key(api_key: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM tenants WHERE api_key=%s AND is_active=TRUE", (api_key,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close(); conn.close()

@router.get("/list")
def list_tenants():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT id, name, slug, plan, is_active, created_at FROM tenants ORDER BY id")
        tenants = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return error_response("DB error", "DB_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Tenants", {"count": len(tenants), "tenants": tenants})

@router.post("/create")
def create_tenant(data: TenantCreate):
    conn = get_db()
    cur = conn.cursor()
    try:
        import secrets
        api_key = data.api_key or secrets.token_hex(16)
        cur.execute(
            "INSERT INTO tenants (name, slug) VALUES (%s,%s) RETURNING id",
            (data.name, data.code)
        )
        new_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Create failed", "CREATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Tenant created", {"id": new_id, "slug": data.code, "api_key": api_key})

@router.get("/me")
def get_my_tenant(x_api_key: Optional[str] = Header(None)):
    if not x_api_key:
        return error_response("API key required", "AUTH_ERROR", "Pass X-Api-Key header")
    tenant = get_tenant_by_key(x_api_key)
    if not tenant:
        return error_response("Invalid API key", "AUTH_ERROR", "")
    return ok_response("Tenant info", tenant)

@router.get("/{tenant_code}/drafts")
def tenant_drafts(tenant_code: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT jd.* FROM journal_drafts jd
            JOIN tenants t ON t.id = jd.tenant_id
            WHERE t.slug = %s
            ORDER BY jd.created_at DESC LIMIT 50
        """, (tenant_code,))
        drafts = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return error_response("DB error", "DB_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response(f"Drafts for {tenant_code}", {"count": len(drafts), "drafts": drafts})
