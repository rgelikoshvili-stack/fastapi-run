from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
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

router = APIRouter(prefix="/settings", tags=["settings"])

class SettingUpdate(BaseModel):
    key: str
    value: str

@router.get("/", response_class=HTMLResponse)
def settings_page():
    return open("app/templates/settings.html", encoding="utf-8").read()
@router.post("/save")
def save_setting(payload: SettingUpdate, db: Session = Depends(get_db)):
    db.execute(text("INSERT INTO settings (key, value, updated_at) VALUES (:key, :value, NOW()) ON CONFLICT (key) DO UPDATE SET value=:value, updated_at=NOW()"), {"key": payload.key, "value": payload.value})
    db.commit()
    return {"message": "saved", "key": payload.key}

@router.get("/load")
def load_settings(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT key, value FROM settings")).fetchall()
    return {r[0]: r[1] for r in rows}
