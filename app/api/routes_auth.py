from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

limiter = Limiter(key_func=get_remote_address)
import hashlib, secrets, string, uuid
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

DB_URL = "postgresql://postgres:BridgeHub2026x@35.192.214.120:5432/bridgehub"
engine = create_engine(DB_URL, connect_args={"connect_timeout": 10})
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def generate_api_key():
    return "bh_live_" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

def hash_key(raw):
    return hashlib.sha256(raw.encode()).hexdigest()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def require_api_key(raw_key: Optional[str] = Security(api_key_header), db: Session = Depends(get_db)):
    if not raw_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    row = db.execute(text("SELECT id, key_prefix, name, owner, scopes, expires_at FROM api_keys WHERE key_hash = :h AND is_active = TRUE"), {"h": hash_key(raw_key)}).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    try:
        db.execute(text("UPDATE api_keys SET last_used = NOW() WHERE key_hash = :h"), {"h": hash_key(raw_key)})
        db.commit()
    except Exception:
        db.rollback()
    return row

class KeyCreate(BaseModel):
    name: str = Field(..., example="client-mobile")
    owner: Optional[str] = None
    scopes: Optional[str] = "read,write"
    expires_days: Optional[int] = None

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/keys", status_code=201)
@limiter.limit("5/minute")
def create_key(request: Request, payload: KeyCreate, db: Session = Depends(get_db)):
    raw = generate_api_key()
    kh = hash_key(raw)
    prefix = raw[:14]
    key_id = str(uuid.uuid4())
    expires = None
    if payload.expires_days:
        expires = datetime.utcnow() + timedelta(days=payload.expires_days)
    db.execute(text("INSERT INTO api_keys (id, key_hash, key_prefix, name, owner, scopes, is_active, created_at, expires_at) VALUES (:id, :kh, :prefix, :name, :owner, :scopes, TRUE, NOW(), :expires)"),
        {"id": key_id, "kh": kh, "prefix": prefix, "name": payload.name, "owner": payload.owner, "scopes": payload.scopes or "read,write", "expires": expires})
    db.commit()
    return {"id": key_id, "api_key": raw, "key_prefix": prefix, "name": payload.name, "warning": "Save this key now. It will NOT be shown again."}

@router.get("/verify")
@limiter.limit("60/minute")
def verify(request: Request, key=Depends(require_api_key)):
    return {"valid": True, "key_prefix": key.key_prefix, "name": key.name, "scopes": key.scopes}
    

@router.get("/me")
def me(key=Depends(require_api_key)):
    return {"key_prefix": key.key_prefix, "name": key.name, "owner": key.owner, "scopes": key.scopes}

@router.get("/keys")
def list_keys(db: Session = Depends(get_db), _=Depends(require_api_key)):
    rows = db.execute(text("SELECT id, key_prefix, name, owner, scopes, is_active, created_at, last_used, expires_at FROM api_keys ORDER BY created_at DESC")).fetchall()
    return {"total": len(rows), "keys": [{"id": str(r.id), "key_prefix": r.key_prefix, "name": r.name, "is_active": r.is_active} for r in rows]}

@router.delete("/keys/{key_id}")
def revoke_key(key_id: str, db: Session = Depends(get_db), _=Depends(require_api_key)):
    result = db.execute(text("UPDATE api_keys SET is_active = FALSE WHERE id = :id"), {"id": key_id})
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Key not found")
    return {"revoked": True, "id": key_id}