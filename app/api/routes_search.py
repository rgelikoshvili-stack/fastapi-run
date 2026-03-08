from fastapi import APIRouter
import psycopg2, psycopg2.extras
from datetime import datetime
from app.api.db import get_db

router = APIRouter(prefix="/search", tags=["search"])



def ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS search_index (
            id SERIAL PRIMARY KEY,
            doc_id VARCHAR(100),
            doc_type VARCHAR(50),
            filename VARCHAR(300),
            
            amount FLOAT,
            state VARCHAR(50),
            tags TEXT[],
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id SERIAL PRIMARY KEY,
            query TEXT,
            results_count INT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

@router.post("/query")
def search(q: str = "", state: str = "", min_amount: float = 0, max_amount: float = 999999999):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()

    conditions = ["1=1"]
    params = []

    if q:
        conditions.append("(filename ILIKE %s )")
        params += [f"%{q}%"]
    if state:
        conditions.append("state = %s")
        params.append(state)

    where = " AND ".join(conditions)
    cur.execute(f"""
        SELECT p.run_id, p.filename, p.state, p.created_at
        FROM pipeline_runs p
        WHERE {where}
        ORDER BY p.created_at DESC LIMIT 50
    """, params)
    docs = [dict(r) for r in cur.fetchall()]

    # Bank transactions search
    tx_results = []
    if q:
        cur.execute("""
            SELECT id, bank, date, amount, description
            FROM bank_transactions
            WHERE description ILIKE %s
            ORDER BY created_at DESC LIMIT 20
        """, (f"%{q}%",))
        tx_results = [dict(r) for r in cur.fetchall()]

    # COA search
    coa_results = []
    if q:
        cur.execute("""
            SELECT code, name_ka, name_en, category
            FROM coa
            WHERE name_ka ILIKE %s OR name_en ILIKE %s OR code ILIKE %s
        """, (f"%{q}%", f"%{q}%", f"%{q}%"))
        coa_results = [dict(r) for r in cur.fetchall()]

    # Log search
    cur.execute("INSERT INTO search_history (query, results_count) VALUES (%s,%s)",
        (q, len(docs) + len(tx_results) + len(coa_results)))
    conn.commit()
    cur.close(); conn.close()

    return {
        "ok": True,
        "query": q,
        "total_results": len(docs) + len(tx_results) + len(coa_results),
        "documents": docs,
        "transactions": tx_results,
        "coa_accounts": coa_results
    }

@router.get("/filters")
def get_filters():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("SELECT DISTINCT state FROM pipeline_runs WHERE state IS NOT NULL")
    statees = [r["state"] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT bank FROM bank_transactions WHERE bank IS NOT NULL")
    banks = [r["bank"] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT category FROM coa WHERE category IS NOT NULL")
    categories = [r["category"] for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "statees": statees, "banks": banks, "coa_categories": categories}

@router.get("/recent")
def recent_searches():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("""
        SELECT query, results_count, created_at
        FROM search_history
        ORDER BY created_at DESC LIMIT 20
    """)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"ok": True, "recent_searches": rows}

@router.get("/stats")
def search_stats():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_tables(cur)
    conn.commit()
    cur.execute("SELECT COUNT(*) as total FROM pipeline_runs")
    total_docs = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as total FROM bank_transactions")
    total_txs = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as total FROM coa")
    total_coa = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as total FROM search_history")
    total_searches = cur.fetchone()["total"]
    cur.close(); conn.close()
    return {
        "ok": True,
        "indexed": {
            "documents": total_docs,
            "transactions": total_txs,
            "coa_accounts": total_coa,
            "total": total_docs + total_txs + total_coa
        },
        "total_searches": total_searches
    }