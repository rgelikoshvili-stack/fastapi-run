from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from app.api.db import get_db

DB_URL = "postgresql://postgres:BridgeHub2026x@35.192.214.120:5432/bridgehub"
engine = create_engine(DB_URL, connect_args={"connect_timeout": 10})
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

router = APIRouter(prefix="/users", tags=["users"])

class UserCreate(BaseModel):
    email: str
    name: Optional[str] = None
    role: Optional[str] = "viewer"

@router.post("/", status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    db.execute(text("INSERT INTO users (email, name, role) VALUES (:email, :name, :role)"),
               {"email": payload.email, "name": payload.name, "role": payload.role})
    db.commit()
    return {"message": "User created", "email": payload.email}

@router.get("/")
def list_users(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT id, email, name, role, is_active, created_at FROM users")).fetchall()
    return [{"id": str(r[0]), "email": r[1], "name": r[2], "role": r[3], "is_active": r[4]} for r in rows]

@router.get("/{user_id}")
def get_user(user_id: str, db: Session = Depends(get_db)):
    row = db.execute(text("SELECT id, email, name, role, is_active FROM users WHERE id=:id"), {"id": user_id}).fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    return {"id": str(row[0]), "email": row[1], "name": row[2], "role": row[3], "is_active": row[4]}

@router.delete("/{user_id}")
def deactivate_user(user_id: str, db: Session = Depends(get_db)):
    db.execute(text("UPDATE users SET is_active=FALSE WHERE id=:id"), {"id": user_id})
    db.commit()
    return {"message": "User deactivated"}