import os, hashlib, secrets, psycopg2
from psycopg2.extras import RealDictCursor

ROLES = ("admin", "accountant", "reviewer", "ai_supervisor")

def _get_db():
    return psycopg2.connect(os.environ["DATABASE_URL"])

def create_users_table():
    conn = _get_db()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                tenant_id VARCHAR(100) DEFAULT 'default',
                role VARCHAR(50) DEFAULT 'accountant',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                last_login TIMESTAMP,
                UNIQUE(email, tenant_id)
            )
        """)
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{h}"

def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, h = password_hash.split(":", 1)
        return hashlib.sha256(f"{salt}{password}".encode()).hexdigest() == h
    except Exception:
        return False

def get_user(email: str, tenant_id: str = "default"):
    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM users
                WHERE email = %s AND tenant_id = %s AND is_active = TRUE
            """, (email, tenant_id))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()

def create_user(email: str, password: str, tenant_id: str = "default", role: str = "accountant"):
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO users (email, password_hash, tenant_id, role)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (email, tenant_id) DO NOTHING
                RETURNING *
            """, (email, hash_password(password), tenant_id, role))
            row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None
    finally:
        conn.close()

def update_last_login(user_id: int):
    conn = _get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET last_login=NOW() WHERE id=%s", (user_id,))
        conn.commit()
    finally:
        conn.close()

PERMISSIONS = {
    "admin":        ["approve","reject","correct","view","settings","manage_users","override_patterns"],
    "accountant":   ["approve","reject","correct","view"],
    "reviewer":     ["view","correct"],
    "ai_supervisor":["view","override_patterns","manage_patterns"],
}

def has_permission(role: str, action: str) -> bool:
    return action in PERMISSIONS.get(role, [])
