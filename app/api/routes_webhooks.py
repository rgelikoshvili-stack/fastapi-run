from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
import httpx, uuid
from datetime import datetime, timezone

DB_URL = "postgresql://postgres:BridgeHub2026x@35.192.214.120:5432/bridgehub"
engine = create_engine(DB_URL, connect_args={"connect_timeout": 10})
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

class WebhookCreate(BaseModel):
    url: str
    event: str
    name: Optional[str] = None

@router.post("/", status_code=201)
def create_webhook(payload: WebhookCreate, db: Session = Depends(get_db)):
    wid = str(uuid.uuid4())
    db.execute(text("INSERT INTO webhooks (id, url, event, name) VALUES (:id, :url, :event, :name)"),
               {"id": wid, "url": payload.url, "event": payload.event, "name": payload.name})
    db.commit()
    return {"id": wid, "url": payload.url, "event": payload.event}

@router.get("/")
def list_webhooks(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT id, url, event, name, is_active FROM webhooks")).fetchall()
    return [{"id": str(r[0]), "url": r[1], "event": r[2], "name": r[3], "is_active": r[4]} for r in rows]

@router.delete("/{webhook_id}")
def delete_webhook(webhook_id: str, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM webhooks WHERE id=:id"), {"id": webhook_id})
    db.commit()
    return {"message": "Webhook deleted"}

@router.post("/trigger/{event}")
def trigger_webhook(event: str, db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT url FROM webhooks WHERE event=:event AND is_active=TRUE"), {"event": event}).fetchall()
    results = []
    for row in rows:
        try:
            r = httpx.post(row[0], json={"event": event, "timestamp": datetime.now(timezone.utc).isoformat()}, timeout=5)
            results.append({"url": row[0], "status": r.status_code})
        except:
            results.append({"url": row[0], "status": "failed"})
    return {"triggered": len(results), "results": results}