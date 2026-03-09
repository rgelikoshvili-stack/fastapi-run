from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from app.api.db import get_db
import psycopg2.extras

router = APIRouter(prefix="/ui", tags=["ui"])

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT status, COUNT(*) as cnt FROM journal_drafts GROUP BY status")
        stats = {r["status"]: r["cnt"] for r in cur.fetchall()}
        cur.execute("SELECT * FROM journal_drafts ORDER BY created_at DESC LIMIT 20")
        drafts = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT * FROM audit_log ORDER BY COALESCE(event_time, created_at) DESC LIMIT 10")
        events = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    drafted = stats.get("drafted", 0)
    approved = stats.get("approved", 0)
    pending = stats.get("pending_approval", 0)
    total = sum(stats.values())

    rows_html = ""
    for d in drafts:
        color = {"approved":"#22c55e","drafted":"#3b82f6","pending_approval":"#f59e0b","rejected":"#ef4444"}.get(d.get("status",""),"#888")
        rows_html += f"<tr><td>{d.get('id')}</td><td>{str(d.get('date',''))[:10]}</td><td>{str(d.get('description',''))[:40]}</td><td>{d.get('partner','')}</td><td>{d.get('debit_account','')}</td><td>{d.get('credit_account','')}</td><td>{d.get('amount','')}</td><td><span style='color:{color};font-weight:bold'>{d.get('status','')}</span></td></tr>"

    audit_html = ""
    for e in events:
        audit_html += f"<tr><td>{str(e.get('event_time') or e.get('created_at',''))[:19]}</td><td>{e.get('action') or e.get('event_type','')}</td><td>{e.get('actor','system')}</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="ka">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bridge Hub Dashboard</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0}}
  .header{{background:#1e293b;padding:20px 30px;border-bottom:2px solid #3b82f6;display:flex;justify-content:space-between;align-items:center}}
  .header h1{{color:#3b82f6;font-size:24px}}
  .container{{padding:24px 30px}}
  .cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}}
  .card{{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155}}
  .card .label{{color:#94a3b8;font-size:12px;text-transform:uppercase;margin-bottom:8px}}
  .card .value{{font-size:32px;font-weight:bold}}
  .blue{{color:#3b82f6}}.green{{color:#22c55e}}.yellow{{color:#f59e0b}}
  .links{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}}
  .link{{background:#1e293b;border:1px solid #3b82f6;color:#3b82f6;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:13px}}
  .link:hover{{background:#3b82f6;color:white}}
  .section{{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155;margin-bottom:20px}}
  .section h2{{color:#94a3b8;font-size:13px;text-transform:uppercase;margin-bottom:16px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{background:#0f172a;color:#94a3b8;padding:10px;text-align:left;border-bottom:1px solid #334155}}
  td{{padding:10px;border-bottom:1px solid #0f172a}}
  .btn{{background:#3b82f6;color:white;border:none;padding:8px 16px;border-radius:8px;cursor:pointer}}
</style>
</head>
<body>
<div class="header">
  <div><h1>Bridge Hub</h1></div>
  <button class="btn" onclick="location.reload()">Refresh</button>
</div>
<div class="container">
  <div class="links">
    <a class="link" href="/docs" target="_blank">API Docs</a>
    <a class="link" href="/approval/queue" target="_blank">Approval Queue</a>
    <a class="link" href="/ui/dashboard/v2" target="_blank">Dashboard v2</a>
    <a class="link" href="/ui/mobile" target="_blank">Mobile</a>
    <a class="link" href="/ui/reports" target="_blank">Reports</a>
    <a class="link" href="/export/journal/excel" target="_blank">Excel</a>
  </div>
  <div class="cards">
    <div class="card"><div class="label">Total Drafts</div><div class="value blue">{total}</div></div>
    <div class="card"><div class="label">Approved</div><div class="value green">{approved}</div></div>
    <div class="card"><div class="label">Drafted</div><div class="value blue">{drafted}</div></div>
    <div class="card"><div class="label">Pending</div><div class="value yellow">{pending}</div></div>
  </div>
  <div class="section">
    <h2>Journal Drafts (last 20)</h2>
    <table>
      <thead><tr><th>ID</th><th>Date</th><th>Description</th><th>Partner</th><th>Dr</th><th>Cr</th><th>Amount</th><th>Status</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
  <div class="section">
    <h2>Audit Log (last 10)</h2>
    <table>
      <thead><tr><th>Time</th><th>Action</th><th>Actor</th></tr></thead>
      <tbody>{audit_html}</tbody>
    </table>
  </div>
</div>
</body>
</html>"""
    return HTMLResponse(content=html)