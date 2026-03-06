from fastapi import APIRouter
import psycopg2, psycopg2.extras, os
from openai import OpenAI

router = APIRouter(prefix="/strategy", tags=["strategy"])

def get_db():
    return psycopg2.connect(host="35.192.214.120", dbname="bridgehub", user="postgres", password="BridgeHub2026x")

def get_financial_snapshot():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COUNT(*) as total FROM pipeline_runs")
    total_docs = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as approved FROM pipeline_runs WHERE status='APPROVED'")
    approved = cur.fetchone()["approved"]
    cur.execute("SELECT COUNT(*) as pending FROM pipeline_runs WHERE status='PENDING_APPROVAL'")
    pending = cur.fetchone()["pending"]
    cur.execute("SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) as inflow FROM bank_transactions")
    inflow = float(cur.fetchone()["inflow"])
    cur.execute("SELECT COALESCE(SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END),0) as outflow FROM bank_transactions")
    outflow = float(cur.fetchone()["outflow"])
    cur.execute("SELECT COUNT(*) as total FROM bank_transactions")
    total_txs = cur.fetchone()["total"]
    cur.close(); conn.close()
    return {
        "total_documents": total_docs,
        "approved": approved,
        "pending": pending,
        "total_transactions": total_txs,
        "total_inflow_gel": round(inflow, 2),
        "total_outflow_gel": round(outflow, 2),
        "net_cashflow_gel": round(inflow - outflow, 2),
        "approval_rate": round(approved / total_docs * 100, 1) if total_docs > 0 else 0
    }

@router.get("/cfo-report")
def cfo_report():
    snapshot = get_financial_snapshot()
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    prompt = f"""შენ ხარ AI CFO Assistant Bridge Hub სისტემაში.
    
მიმდინარე ფინანსური მდგომარეობა:
- სულ დოკუმენტები: {snapshot['total_documents']}
- დამტკიცებული: {snapshot['approved']} ({snapshot['approval_rate']}%)
- მოლოდინში: {snapshot['pending']}
- სულ ტრანზაქციები: {snapshot['total_transactions']}
- შემოსავალი: {snapshot['total_inflow_gel']} GEL
- გასავალი: {snapshot['total_outflow_gel']} GEL
- სუფთა cashflow: {snapshot['net_cashflow_gel']} GEL

გთხოვ მოამზადო მოკლე CFO რეპორტი ქართულ ენაზე:
1. მდგომარეობის შეფასება
2. რისკები
3. რეკომენდაციები
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500
    )
    report = response.choices[0].message.content
    return {"ok": True, "snapshot": snapshot, "cfo_report": report}

@router.get("/recommendations")
def get_recommendations():
    snapshot = get_financial_snapshot()
    recs = []
    if snapshot["pending"] > 5:
        recs.append({"priority": "HIGH", "action": "დაჩქარდეს approval პროცესი", "reason": f"{snapshot['pending']} დოკუმენტი ელოდება"})
    if snapshot["net_cashflow_gel"] < 0:
        recs.append({"priority": "CRITICAL", "action": "Cashflow უარყოფითია", "reason": f"ნეტო: {snapshot['net_cashflow_gel']} GEL"})
    if snapshot["approval_rate"] < 80:
        recs.append({"priority": "MEDIUM", "action": "გაუმჯობესდეს approval rate", "reason": f"მიმდინარე: {snapshot['approval_rate']}%"})
    if not recs:
        recs.append({"priority": "LOW", "action": "სისტემა სტაბილურია", "reason": "ყველა მაჩვენებელი ნორმაშია"})
    return {"ok": True, "snapshot": snapshot, "recommendations": recs}

@router.get("/status")
def strategy_status():
    snapshot = get_financial_snapshot()
    health = "CRITICAL" if snapshot["net_cashflow_gel"] < 0 else "WARNING" if snapshot["pending"] > 10 else "HEALTHY"
    return {"ok": True, "health": health, "snapshot": snapshot}