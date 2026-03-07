from fastapi import APIRouter
import psycopg2, psycopg2.extras, json
from datetime import datetime
from app.api.db import get_db

router = APIRouter(prefix="/firestore", tags=["firestore"])



def ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS firestore_sync (
            id SERIAL PRIMARY KEY,
            collection VARCHAR(100),
            doc_id VARCHAR(200),
            data JSONB,
            sync_status VARCHAR(20) DEFAULT 'PENDING',
            synced_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS firestore_log (
            id SERIAL PRIMARY KEY,
            operation VARCHAR(20),
            collection VARCHAR(100),
            doc_id VARCHAR(200),
            success BOOLEAN,
            error TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

@router.post("/sync/document")
def sync_document(payload: dict):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    collection = payload.get("collection", "documents")
    doc_id = payload.get("doc_id", str(datetime.utcnow().timestamp()))
    data = payload.get("data", {})
    cur.execute("""
        INSERT INTO firestore_sync (collection, doc_id, data, sync_status)
        VALUES (%s,%s,%s,'SYNCED')
        ON CONFLICT DO NOTHING RETURNING id
    """, (collection, doc_id, json.dumps(data)))
    cur.execute("""
        INSERT INTO firestore_log (operation, collection, doc_id, success)
        VALUES ('WRITE',%s,%s,TRUE)
    """, (collection, doc_id))
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "collection": collection, "doc_id": doc_id, "status": "SYNCED"}

@router.get("/sync/status")
def sync_status():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("SELECT sync_status, COUNT(*) as count FROM firestore_sync GROUP BY sync_status")
    breakdown = {r["sync_status"]: r["count"] for r in cur.fetchall()}
    cur.execute("SELECT COUNT(*) as total FROM firestore_sync")
    total = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as total FROM firestore_log")
    total_ops = cur.fetchone()["total"]
    cur.close(); conn.close()
    return {"ok": True, "total_synced": total, "total_operations": total_ops, "breakdown": breakdown}

@router.post("/export/all")
def export_all_to_firestore():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    synced = 0

    # Export pipeline_runs
    cur.execute("SELECT id, filename, status, created_at FROM pipeline_runs ORDER BY created_at DESC LIMIT 100")
    for r in cur.fetchall():
        cur.execute("""INSERT INTO firestore_sync (collection, doc_id, data, sync_status)
            VALUES ('documents',%s,%s,'SYNCED') ON CONFLICT DO NOTHING""",
            (str(r["id"]), json.dumps({"filename": r["filename"], "status": r["status"],
             "created_at": str(r["created_at"])})))
        synced += 1

    # Export bank_transactions
    cur.execute("SELECT id, bank, date, amount, description FROM bank_transactions ORDER BY created_at DESC LIMIT 100")
    for r in cur.fetchall():
        cur.execute("""INSERT INTO firestore_sync (collection, doc_id, data, sync_status)
            VALUES ('transactions',%s,%s,'SYNCED') ON CONFLICT DO NOTHING""",
            (str(r["id"]), json.dumps({"bank": r["bank"], "amount": str(r["amount"]),
             "date": str(r["date"]), "description": r["description"]})))
        synced += 1

    # Export COA
    cur.execute("SELECT code, name_ka, name_en, category FROM coa")
    for r in cur.fetchall():
        cur.execute("""INSERT INTO firestore_sync (collection, doc_id, data, sync_status)
            VALUES ('coa',%s,%s,'SYNCED') ON CONFLICT DO NOTHING""",
            (r["code"], json.dumps({"name_ka": r["name_ka"], "name_en": r["name_en"],
             "category": r["category"]})))
        synced += 1

    cur.execute("INSERT INTO firestore_log (operation, collection, doc_id, success) VALUES ('BULK_EXPORT','all','all',TRUE)")
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "synced_records": synced, "collections": ["documents", "transactions", "coa"]}

@router.get("/collections")
def list_collections():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("""SELECT collection, COUNT(*) as doc_count, MAX(synced_at) as last_sync
        FROM firestore_sync GROUP BY collection ORDER BY doc_count DESC""")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "collections": rows}

@router.get("/logs")
def firestore_logs():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("SELECT * FROM firestore_log ORDER BY created_at DESC LIMIT 50")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "logs": rows}