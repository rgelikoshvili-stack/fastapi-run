from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from app.api.db import get_db
import psycopg2.extras, json

router = APIRouter(prefix="/ui", tags=["ui"])

@router.get("/mobile", response_class=HTMLResponse)
def mobile_dashboard():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT status, COUNT(*) as cnt, COALESCE(SUM(amount),0) as total FROM journal_drafts GROUP BY status")
        stats = {r["status"]: {"count": r["cnt"], "total": float(r["total"])} for r in cur.fetchall()}
        cur.execute("SELECT COALESCE(SUM(amount),0) FROM journal_drafts WHERE account_code LIKE '6%'")
        income = float(cur.fetchone()["coalesce"])
        cur.execute("SELECT COALESCE(SUM(amount),0) FROM journal_drafts WHERE account_code LIKE '7%'")
        expense = float(cur.fetchone()["coalesce"])
        cur.execute("SELECT * FROM journal_drafts ORDER BY created_at DESC LIMIT 8")
        recent = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) FROM invoices")
        inv_count = cur.fetchone()["count"]
        cur.execute("SELECT COALESCE(SUM(total),0) FROM invoices WHERE status='paid'")
        inv_paid = float(cur.fetchone()["coalesce"])
        cur.execute("SELECT COUNT(*) FROM journal_drafts WHERE status='pending_approval'")
        pending = cur.fetchone()["count"]
    finally:
        cur.close(); conn.close()

    total_tx = sum(v["count"] for v in stats.values())
    approved = stats.get("approved", {}).get("count", 0)
    balance = round(income - expense, 2)

    rows = ""
    for d in recent:
        color = {"approved":"#22c55e","drafted":"#60a5fa","pending_approval":"#fbbf24","rejected":"#f87171"}.get(d.get("status",""),"#9ca3af")
        rows += f"""
        <div class="tx-item">
          <div class="tx-left">
            <div class="tx-desc">{str(d.get('description',''))[:30]}</div>
            <div class="tx-meta">{str(d.get('date',''))[:10]} · {d.get('partner','') or '—'}</div>
          </div>
          <div class="tx-right">
            <div class="tx-amount">₾{d.get('amount','')}</div>
            <div class="tx-status" style="color:{color}">●&nbsp;{d.get('status','')}</div>
          </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="ka">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Bridge Hub</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#f1f5f9;max-width:480px;margin:0 auto;min-height:100vh}}
.header{{background:#1e293b;padding:16px 20px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:10;border-bottom:1px solid #334155}}
.header h1{{font-size:18px;color:#60a5fa;font-weight:700}}
.header .badge{{background:#ef4444;color:white;border-radius:12px;padding:2px 8px;font-size:12px}}
.container{{padding:16px}}
.balance-card{{background:linear-gradient(135deg,#1d4ed8,#4f46e5);border-radius:20px;padding:24px 20px;margin-bottom:16px}}
.balance-label{{font-size:13px;color:#bfdbfe;margin-bottom:4px}}
.balance-amount{{font-size:36px;font-weight:700;color:white}}
.balance-sub{{font-size:13px;color:#bfdbfe;margin-top:8px;display:flex;gap:16px}}
.kpi-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px}}
.kpi{{background:#1e293b;border-radius:14px;padding:14px;border:1px solid #334155}}
.kpi .label{{font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}}
.kpi .value{{font-size:22px;font-weight:700}}
.kpi.green .value{{color:#22c55e}}
.kpi.red .value{{color:#f87171}}
.kpi.blue .value{{color:#60a5fa}}
.kpi.yellow .value{{color:#fbbf24}}
.section-title{{font-size:13px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px;padding:0 4px}}
.tx-list{{background:#1e293b;border-radius:14px;overflow:hidden;margin-bottom:16px;border:1px solid #334155}}
.tx-item{{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid #1e293b}}
.tx-item:last-child{{border-bottom:none}}
.tx-item:active{{background:#0f172a}}
.tx-desc{{font-size:14px;color:#f1f5f9;font-weight:500}}
.tx-meta{{font-size:12px;color:#64748b;margin-top:2px}}
.tx-amount{{font-size:14px;font-weight:700;color:#f1f5f9;text-align:right}}
.tx-status{{font-size:11px;text-align:right;margin-top:2px}}
.quick-links{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px}}
.ql{{background:#1e293b;border-radius:12px;padding:12px 8px;text-align:center;text-decoration:none;border:1px solid #334155;display:block}}
.ql:active{{background:#0f172a}}
.ql .icon{{font-size:22px;margin-bottom:4px}}
.ql .text{{font-size:11px;color:#94a3b8}}
.refresh-btn{{width:100%;background:#3b82f6;color:white;border:none;padding:14px;border-radius:14px;font-size:15px;font-weight:600;cursor:pointer;margin-bottom:20px}}
.refresh-btn:active{{background:#2563eb}}
</style>
</head>
<body>
<div class="header">
  <h1>🌉 Bridge Hub</h1>
  <span class="badge">{pending} pending</span>
</div>
<div class="container">

  <div class="balance-card">
    <div class="balance-label">Net Balance</div>
    <div class="balance-amount">₾{balance:,.0f}</div>
    <div class="balance-sub">
      <span>↑ ₾{income:,.0f} income</span>
      <span>↓ ₾{expense:,.0f} expense</span>
    </div>
  </div>

  <div class="kpi-grid">
    <div class="kpi blue"><div class="label">Transactions</div><div class="value">{total_tx}</div></div>
    <div class="kpi green"><div class="label">Approved</div><div class="value">{approved}</div></div>
    <div class="kpi yellow"><div class="label">Invoices</div><div class="value">{inv_count}</div></div>
    <div class="kpi green"><div class="label">Paid</div><div class="value">₾{inv_paid:,.0f}</div></div>
  </div>

  <div class="section-title">Quick Actions</div>
  <div class="quick-links">
    <a class="ql" href="/docs" target="_blank"><div class="icon">📖</div><div class="text">API Docs</div></a>
    <a class="ql" href="/approval/queue" target="_blank"><div class="icon">📋</div><div class="text">Queue</div></a>
    <a class="ql" href="/export/journal/excel" target="_blank"><div class="icon">📊</div><div class="text">Excel</div></a>
    <a class="ql" href="/reports/pdf" target="_blank"><div class="icon">📄</div><div class="text">PDF</div></a>
    <a class="ql" href="/ui/dashboard/v2" target="_blank"><div class="icon">📈</div><div class="text">Charts</div></a>
    <a class="ql" href="/api-docs/postman" target="_blank"><div class="icon">🔗</div><div class="text">Postman</div></a>
  </div>

  <div class="section-title">Recent Transactions</div>
  <div class="tx-list">{rows}</div>

  <button class="refresh-btn" onclick="location.reload()">↻ Refresh</button>
</div>
</body>
</html>"""
    return HTMLResponse(content=html)
