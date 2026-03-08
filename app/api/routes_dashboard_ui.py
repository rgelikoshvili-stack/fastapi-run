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
        cur.execute("SELECT * FROM audit_events ORDER BY created_at DESC LIMIT 10")
        events = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    drafted = stats.get("drafted", 0)
    approved = stats.get("approved", 0)
    pending = stats.get("pending_approval", 0)
    rejected = stats.get("rejected", 0)
    total = sum(stats.values())

    rows_html = ""
    for d in drafts:
        status_color = {
            "approved": "#22c55e",
            "drafted": "#3b82f6",
            "pending_approval": "#f59e0b",
            "rejected": "#ef4444"
        }.get(d.get("status",""), "#888")
        rows_html += f"""
        <tr>
          <td>{d.get('id')}</td>
          <td>{str(d.get('date',''))[:10]}</td>
          <td>{str(d.get('description',''))[:40]}</td>
          <td>{d.get('partner','')}</td>
          <td>{d.get('debit_account','')}</td>
          <td>{d.get('credit_account','')}</td>
          <td>{d.get('amount','')}</td>
          <td><span style="color:{status_color};font-weight:bold">{d.get('status','')}</span></td>
        </tr>"""

    audit_html = ""
    for e in events:
        audit_html += f"<tr><td>{str(e.get('created_at',''))[:19]}</td><td>{e.get('event_type','')}</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="ka">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bridge Hub Dashboard</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: Arial, sans-serif; background:#0f172a; color:#e2e8f0; }}
  .header {{ background:#1e293b; padding:20px 30px; border-bottom:2px solid #3b82f6; display:flex; align-items:center; gap:15px; }}
  .header h1 {{ color:#3b82f6; font-size:24px; }}
  .header span {{ color:#94a3b8; font-size:14px; }}
  .container {{ padding:24px 30px; }}
  .cards {{ display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px; }}
  .card {{ background:#1e293b; border-radius:12px; padding:20px; border:1px solid #334155; }}
  .card .label {{ color:#94a3b8; font-size:13px; margin-bottom:8px; }}
  .card .value {{ font-size:32px; font-weight:bold; }}
  .card.blue .value {{ color:#3b82f6; }}
  .card.green .value {{ color:#22c55e; }}
  .card.yellow .value {{ color:#f59e0b; }}
  .card.red .value {{ color:#ef4444; }}
  .section {{ background:#1e293b; border-radius:12px; padding:20px; border:1px solid #334155; margin-bottom:20px; }}
  .section h2 {{ color:#94a3b8; font-size:14px; text-transform:uppercase; letter-spacing:1px; margin-bottom:16px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ background:#0f172a; color:#94a3b8; padding:10px 12px; text-align:left; border-bottom:1px solid #334155; }}
  td {{ padding:10px 12px; border-bottom:1px solid #1e293b; }}
  tr:hover td {{ background:#0f172a; }}
  .badge {{ display:inline-block; padding:3px 10px; border-radius:20px; font-size:12px; }}
  .refresh {{ float:right; background:#3b82f6; color:white; border:none; padding:8px 16px; border-radius:8px; cursor:pointer; font-size:13px; }}
  .refresh:hover {{ background:#2563eb; }}
  .api-links {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:20px; }}
  .api-link {{ background:#1e293b; border:1px solid #3b82f6; color:#3b82f6; padding:8px 16px; border-radius:8px; text-decoration:none; font-size:13px; }}
  .api-link:hover {{ background:#3b82f6; color:white; }}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>🌉 Bridge Hub</h1>
    <span>v1.0.0 — Bank Pipeline Dashboard</span>
  </div>
  <button class="refresh" onclick="location.reload()">↻ Refresh</button>
</div>
<div class="container">

  <div class="api-links">
    <a class="api-link" href="/docs" target="_blank">📖 API Docs</a>
    <a class="api-link" href="/approval/queue" target="_blank">📋 Approval Queue</a>
    <a class="api-link" href="/export/journal/excel" target="_blank">📊 Excel Export</a>
    <a class="api-link" href="/docs-hub/sprints" target="_blank">🗂 Sprint History</a>
    <a class="api-link" href="/1c/preview/approved" target="_blank">🔗 1C Preview</a>
  </div>

  <div class="cards">
    <div class="card blue"><div class="label">სულ Journal Drafts</div><div class="value">{total}</div></div>
    <div class="card green"><div class="label">Approved</div><div class="value">{approved}</div></div>
    <div class="card blue"><div class="label">Drafted</div><div class="value">{drafted}</div></div>
    <div class="card yellow"><div class="label">Pending Review</div><div class="value">{pending}</div></div>
  </div>

  <div class="section">
    <h2>📒 Journal Drafts (ბოლო 20)</h2>
    <table>
      <thead><tr><th>ID</th><th>Date</th><th>Description</th><th>Partner</th><th>Dr</th><th>Cr</th><th>Amount</th><th>Status</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>

  <div class="section">
    <h2>🔍 Audit Log (ბოლო 10)</h2>
    <table>
      <thead><tr><th>Time</th><th>Event</th></tr></thead>
      <tbody>{audit_html}</tbody>
    </table>
  </div>

</div>
</body>
</html>"""
    return HTMLResponse(content=html)
