from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from app.api.db import get_db
import psycopg2.extras, json

router = APIRouter(prefix="/ui", tags=["ui"])

@router.get("/dashboard/v2", response_class=HTMLResponse)
def dashboard_v2():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT status, COUNT(*) as cnt, COALESCE(SUM(amount),0) as total FROM journal_drafts GROUP BY status")
        stats = {r["status"]: {"count": r["cnt"], "total": float(r["total"])} for r in cur.fetchall()}

        cur.execute("""
            SELECT reason, COUNT(*) as cnt, COALESCE(SUM(amount),0) as total
            FROM journal_drafts GROUP BY reason ORDER BY total DESC LIMIT 8
        """)
        by_reason = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT DATE_TRUNC('day', created_at) as day, COUNT(*) as cnt
            FROM journal_drafts WHERE created_at >= NOW() - INTERVAL '30 days'
            GROUP BY day ORDER BY day
        """)
        timeline = [{"day": str(r["day"])[:10], "cnt": r["cnt"]} for r in cur.fetchall()]

        cur.execute("SELECT COALESCE(SUM(amount),0) FROM journal_drafts WHERE account_code LIKE '6%'")
        total_income = float(cur.fetchone()["coalesce"])
        cur.execute("SELECT COALESCE(SUM(amount),0) FROM journal_drafts WHERE account_code LIKE '7%'")
        total_expense = float(cur.fetchone()["coalesce"])
        cur.execute("SELECT COUNT(*) FROM journal_drafts")
        total_tx = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) FROM journal_drafts WHERE review_required=TRUE AND status='drafted'")
        needs_review = cur.fetchone()["count"]
        cur.execute("SELECT * FROM journal_drafts ORDER BY created_at DESC LIMIT 10")
        recent = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    reason_labels = json.dumps([r["reason"] for r in by_reason])
    reason_totals = json.dumps([float(r["total"]) for r in by_reason])
    reason_counts = json.dumps([r["cnt"] for r in by_reason])
    timeline_labels = json.dumps([r["day"] for r in timeline])
    timeline_data = json.dumps([r["cnt"] for r in timeline])

    approved = stats.get("approved", {}).get("count", 0)
    drafted = stats.get("drafted", {}).get("count", 0)
    pending = stats.get("pending_approval", {}).get("count", 0)
    rejected = stats.get("rejected", {}).get("count", 0)

    rows = ""
    for d in recent:
        color = {"approved":"#22c55e","drafted":"#3b82f6","pending_approval":"#f59e0b","rejected":"#ef4444"}.get(d.get("status",""),"#888")
        rows += f"<tr><td>{d.get('id')}</td><td>{str(d.get('date',''))[:10]}</td><td>{str(d.get('description',''))[:35]}</td><td>{d.get('debit_account','')}</td><td>{d.get('credit_account','')}</td><td>{d.get('amount','')}</td><td style='color:{color}'>{d.get('status','')}</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="ka">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bridge Hub v2</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:Arial,sans-serif;background:#0f172a;color:#e2e8f0}}
.header{{background:#1e293b;padding:18px 28px;border-bottom:2px solid #3b82f6;display:flex;align-items:center;justify-content:space-between}}
.header h1{{color:#3b82f6;font-size:22px}}
.header span{{color:#94a3b8;font-size:13px}}
.nav{{display:flex;gap:10px}}
.nav a{{color:#3b82f6;text-decoration:none;font-size:13px;padding:6px 12px;border:1px solid #3b82f6;border-radius:6px}}
.nav a:hover{{background:#3b82f6;color:white}}
.container{{padding:22px 28px}}
.kpi{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}}
.kpi-card{{background:#1e293b;border-radius:12px;padding:18px;border:1px solid #334155}}
.kpi-card .label{{color:#94a3b8;font-size:12px;margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px}}
.kpi-card .value{{font-size:28px;font-weight:bold}}
.kpi-card .sub{{color:#64748b;font-size:12px;margin-top:4px}}
.blue .value{{color:#3b82f6}}.green .value{{color:#22c55e}}.yellow .value{{color:#f59e0b}}.red .value{{color:#ef4444}}.purple .value{{color:#a855f7}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:22px}}
.chart-box{{background:#1e293b;border-radius:12px;padding:18px;border:1px solid #334155}}
.chart-box h3{{color:#94a3b8;font-size:13px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:14px}}
.section{{background:#1e293b;border-radius:12px;padding:18px;border:1px solid #334155;margin-bottom:16px}}
.section h3{{color:#94a3b8;font-size:13px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:14px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#0f172a;color:#64748b;padding:9px 11px;text-align:left;border-bottom:1px solid #334155}}
td{{padding:9px 11px;border-bottom:1px solid #1e293b}}
tr:hover td{{background:#0f172a}}
.refresh{{background:#3b82f6;color:white;border:none;padding:8px 16px;border-radius:8px;cursor:pointer;font-size:13px}}
.refresh:hover{{background:#2563eb}}
</style>
</head>
<body>
<div class="header">
  <div><h1>🌉 Bridge Hub</h1><span>v2.0 — Analytics Dashboard</span></div>
  <div style="display:flex;gap:12px;align-items:center">
    <nav class="nav">
      <a href="/docs" target="_blank">📖 API</a>
      <a href="/approval/queue" target="_blank">📋 Queue</a>
      <a href="/export/journal/excel" target="_blank">📊 Excel</a>
      <a href="/ui/dashboard">v1</a>
    </nav>
    <button class="refresh" onclick="location.reload()">↻</button>
  </div>
</div>
<div class="container">
  <div class="kpi">
    <div class="kpi-card green"><div class="label">შემოსავალი</div><div class="value">₾{total_income:,.0f}</div><div class="sub">account 6xxx</div></div>
    <div class="kpi-card red"><div class="label">ხარჯი</div><div class="value">₾{total_expense:,.0f}</div><div class="sub">account 7xxx</div></div>
    <div class="kpi-card blue"><div class="label">სულ ტრანზაქცია</div><div class="value">{total_tx}</div><div class="sub">approved: {approved}</div></div>
    <div class="kpi-card yellow"><div class="label">Review Required</div><div class="value">{needs_review}</div><div class="sub">pending: {pending}</div></div>
  </div>

  <div class="charts">
    <div class="chart-box">
      <h3>📊 ხარჯი კატეგორიების მიხედვით</h3>
      <canvas id="barChart" height="200"></canvas>
    </div>
    <div class="chart-box">
      <h3>📈 ტრანზაქციები (30 დღე)</h3>
      <canvas id="lineChart" height="200"></canvas>
    </div>
  </div>

  <div class="charts">
    <div class="chart-box">
      <h3>🥧 სტატუსი</h3>
      <canvas id="doughnut" height="200"></canvas>
    </div>
    <div class="chart-box">
      <h3>💰 თანხა კატეგორიით</h3>
      <canvas id="horizBar" height="200"></canvas>
    </div>
  </div>

  <div class="section">
    <h3>📒 ბოლო 10 ჩანაწერი</h3>
    <table>
      <thead><tr><th>ID</th><th>Date</th><th>Description</th><th>Dr</th><th>Cr</th><th>Amount</th><th>Status</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>

<script>
const COLORS = ['#3b82f6','#22c55e','#f59e0b','#ef4444','#a855f7','#06b6d4','#f97316','#84cc16'];

new Chart(document.getElementById('barChart'), {{
  type:'bar',
  data:{{labels:{reason_labels},datasets:[{{label:'Count',data:{reason_counts},backgroundColor:COLORS}}]}},
  options:{{responsive:true,plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{color:'#94a3b8'}},grid:{{color:'#1e293b'}}}},y:{{ticks:{{color:'#94a3b8'}},grid:{{color:'#334155'}}}}}}}}
}});

new Chart(document.getElementById('lineChart'), {{
  type:'line',
  data:{{labels:{timeline_labels},datasets:[{{label:'Transactions',data:{timeline_data},borderColor:'#3b82f6',backgroundColor:'rgba(59,130,246,0.1)',fill:true,tension:0.4}}]}},
  options:{{responsive:true,plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{color:'#94a3b8',maxRotation:45}},grid:{{color:'#1e293b'}}}},y:{{ticks:{{color:'#94a3b8'}},grid:{{color:'#334155'}}}}}}}}
}});

new Chart(document.getElementById('doughnut'), {{
  type:'doughnut',
  data:{{labels:['Approved','Drafted','Pending','Rejected'],datasets:[{{data:[{approved},{drafted},{pending},{rejected}],backgroundColor:['#22c55e','#3b82f6','#f59e0b','#ef4444']}}]}},
  options:{{responsive:true,plugins:{{legend:{{position:'bottom',labels:{{color:'#94a3b8'}}}}}}}}
}});

new Chart(document.getElementById('horizBar'), {{
  type:'bar',
  data:{{labels:{reason_labels},datasets:[{{label:'Amount ₾',data:{reason_totals},backgroundColor:COLORS}}]}},
  options:{{indexAxis:'y',responsive:true,plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{color:'#94a3b8'}},grid:{{color:'#334155'}}}},y:{{ticks:{{color:'#94a3b8'}},grid:{{color:'#1e293b'}}}}}}}}
}});
</script>
</body>
</html>"""
    return HTMLResponse(content=html)
