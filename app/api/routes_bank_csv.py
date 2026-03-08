from fastapi import APIRouter, UploadFile, File
from app.api.response_utils import ok_response, error_response
from app.api.bank_statement_parser import parse_csv_bytes, parse_xlsx_bytes, parse_xml_bytes

router = APIRouter(prefix="/bank-csv", tags=["bank"])

@router.post("/upload")
async def upload_bank_file(file: UploadFile = File(...)):
    try:
        content = await file.read()
        name = file.filename.lower()

        if name.endswith(".csv"):
            rows = parse_csv_bytes(content)
        elif name.endswith(".xlsx"):
            rows = parse_xlsx_bytes(content)
        elif name.endswith(".xml"):
            rows = parse_xml_bytes(content)
        else:
            return error_response(
                "Unsupported file format",
                "BANK_FILE_ERROR",
                "Use csv, xlsx or xml"
            )

        return ok_response(
            "Bank statement parsed",
            {
                "filename": file.filename,
                "rows_count": len(rows),
                "transactions": rows[:10]
            }
        )
    except Exception as e:
        return error_response("Bank parse failed", "BANK_PARSE_ERROR", str(e))

@router.get("/history")
def bank_csv_history():
    from app.api.db import get_db
    import psycopg2.extras
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT id, filename, status, created_at 
            FROM pipeline_runs ORDER BY created_at DESC LIMIT 20
        """)
        rows = [dict(r) for r in cur.fetchall()]
    except:
        rows = []
    finally:
        cur.close(); conn.close()
    from app.api.response_utils import ok_response
    return ok_response("Bank CSV history", {"count": len(rows), "history": rows})

@router.get("/search/query")
def bank_csv_search(q: str = "", limit: int = 20):
    from app.api.db import get_db
    import psycopg2.extras
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT * FROM journal_drafts
            WHERE description ILIKE %s OR partner ILIKE %s
            ORDER BY created_at DESC LIMIT %s
        """, (f"%{q}%", f"%{q}%", limit))
        rows = [dict(r) for r in cur.fetchall()]
    except:
        rows = []
    finally:
        cur.close(); conn.close()
    from app.api.response_utils import ok_response
    return ok_response("Search results", {"query": q, "count": len(rows), "results": rows})
