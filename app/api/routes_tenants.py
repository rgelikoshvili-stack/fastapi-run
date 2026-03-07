from fastapi import APIRouter, HTTPException
import psycopg2, psycopg2.extras, hashlib, secrets
from datetime import datetime
from app.api.db import get_db

router = APIRouter(prefix="/tenants", tags=["tenants"])



def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            slug VARCHAR(50) UNIQUE NOT NULL,
            plan VARCHAR(20) DEFAULT 'FREE',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tenant_users (
            id SERIAL PRIMARY KEY,
            tenant_id INT REFERENCES tenants(id),
            email VARCHAR(200) UNIQUE NOT NULL,
            full_name VARCHAR(200),
            role VARCHAR(30) DEFAULT 'VIEWER',
            password_hash VARCHAR(200),
            api_token VARCHAR(100) UNIQUE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS role_permissions (
            id SERIAL PRIMARY KEY,
            role VARCHAR(30),
            permission VARCHAR(100),
            UNIQUE(role, permission)
        )
    """)

def seed_permissions(cur):
    perms = [
        ("ADMIN", "all"),
        ("MANAGER", "pipeline.run"), ("MANAGER", "documents.approve"),
        ("MANAGER", "reports.view"), ("MANAGER", "finance.view"),
        ("ACCOUNTANT", "pipeline.run"), ("ACCOUNTANT", "reports.view"),
        ("ACCOUNTANT", "finance.view"), ("ACCOUNTANT", "coa.view"),
        ("VIEWER", "reports.view"), ("VIEWER", "finance.view"),
    ]
    for role, perm in perms:
        cur.execute("INSERT INTO role_permissions (role, permission) VALUES (%s,%s) ON CONFLICT DO NOTHING", (role, perm))

@router.post("/create")
def create_tenant(payload: dict):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    seed_permissions(cur)
    slug = payload.get("name","").lower().replace(" ","-")
    cur.execute("INSERT INTO tenants (name, slug, plan) VALUES (%s,%s,%s) RETURNING id",
        (payload.get("name"), slug, payload.get("plan","FREE")))
    tid = cur.fetchone()["id"]
    # Create admin user
    token = secrets.token_hex(20)
    cur.execute("""INSERT INTO tenant_users (tenant_id, email, full_name, role, password_hash, api_token)
        VALUES (%s,%s,%s,'ADMIN',%s,%s)""",
        (tid, payload.get("admin_email"), payload.get("admin_name","Admin"),
         hash_password(payload.get("password","admin123")), token))
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "tenant_id": tid, "slug": slug, "admin_token": token}

@router.get("/list")
def list_tenants():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("""SELECT t.*, COUNT(u.id) as user_count 
        FROM tenants t LEFT JOIN tenant_users u ON t.id=u.tenant_id
        GROUP BY t.id ORDER BY t.created_at DESC""")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "tenants": rows}

@router.post("/users/add")
def add_user(payload: dict):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    token = secrets.token_hex(20)
    cur.execute("""INSERT INTO tenant_users (tenant_id, email, full_name, role, password_hash, api_token)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (payload.get("tenant_id"), payload.get("email"), payload.get("full_name",""),
         payload.get("role","VIEWER"), hash_password(payload.get("password","pass123")), token))
    uid = cur.fetchone()["id"]
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "user_id": uid, "api_token": token, "role": payload.get("role","VIEWER")}

@router.get("/users/{tenant_id}")
def get_users(tenant_id: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("""SELECT id, email, full_name, role, is_active, created_at 
        FROM tenant_users WHERE tenant_id=%s ORDER BY created_at DESC""", (tenant_id,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "users": rows}

@router.post("/auth/login")
def login(payload: dict):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("""SELECT u.*, t.name as tenant_name, t.slug 
        FROM tenant_users u JOIN tenants t ON u.tenant_id=t.id
        WHERE u.email=%s AND u.password_hash=%s AND u.is_active=TRUE""",
        (payload.get("email"), hash_password(payload.get("password",""))))
    user = cur.fetchone()
    cur.close(); conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"ok": True, "token": user["api_token"], "role": user["role"],
            "tenant": user["tenant_name"], "name": user["full_name"]}

@router.get("/roles/permissions")
def get_permissions():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    seed_permissions(cur)
    conn.commit()
    cur.execute("SELECT role, array_agg(permission) as permissions FROM role_permissions GROUP BY role")
    rows = {r["role"]: r["permissions"] for r in cur.fetchall()}
    cur.close(); conn.close()
    return {"ok": True, "roles": ["ADMIN","MANAGER","ACCOUNTANT","VIEWER"], "permissions": rows}