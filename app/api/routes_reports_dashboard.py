from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from app.api.db import get_db
import psycopg2.extras
from datetime import datetime

router = APIRouter(prefix="/ui", tags=["ui"])

@router.get("/reports", response_class=HTMLResponse)
def reports_dashboard():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # Invoices
        cur.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(total),0) as total FROM invoices")
        inv = cur.fetchone()
        # Expenses
        cur.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(amount),0) as total FROM expenses")
        exp = cur.fetchone()
        # Contracts
        cur.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(value),0) as total FROM contracts WHERE status='active'")
        cont = cur.fetchone()
        # Bank
        cur.execute("SELECT COALESCE(SUM(balance),0) as total FROM bank_accounts")
        bank = cur.fetchone()
        # P&L
        cur.execute("SELECT COALESCE(SUM(amount),0) as total FROM journal_drafts WHERE debit_account LIKE '6%%'")
        income = cur.fetchone()
        cur.execute("SELECT COALESCE(SUM(amount),0) as total FROM journal_drafts WHERE debit_account LIKE '7%%'")
        expenses_jnl = cur.fetchone()
        # Monthly expenses
        cur.execute("""
            SELECT TO_CHAR(date::date,'Mon') as mon, COALESCE(SUM(amount),0) as total
            FROM expenses WHERE EXTRACT(YEAR FROM date::date)=2026
            GROUP BY TO_CHAR(date::date,'Mon'), EXTRACT(MONTH FROM date::date)
            ORDER BY EXTRACT(MONTH FROM date::date)
        """)
        monthly = cur.fetchall()
        # Contracts by type
        cur.execute("SELECT contract_type, COUNT(*) as cnt FROM contracts GROUP BY contract_type")
        cont_types = cur.fetchall()
        # Audit recent
        cur.execute("SELECT action, actor, COALESCE(event_time, created_at) as ts FROM audit_log ORDER BY COALESCE(event_time, created_at) DESC LIMIT 5")
        audit = cur.fetchall()
    finally:
        cur.close(); conn.close()

    inv_total = float(inv["total"])
    exp_total = float(exp["total"])
    cont_total = float(cont["total"])
    bank_total = float(bank["total"])
    inc_total = float(income["total"])
    expj_total = float(expenses_jnl["total"])
    net = inc_total - expj_total

    monthly_labels = [r["mon"] for r in monthly]
    monthly_data = [float(r["total"]) for r in monthly]

    cont_labels = [r["contract_type"] for r in cont_types]
    cont_data = [int(r["cnt"]) for r in cont_types]

    audit_rows = "".join([
        f'<tr><td>{r["action"]}</td><td>{r["actor"]}</td><td>{str(r["ts"])[:16]}</td></tr>'
        for r in audit
    ])

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="ka">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bridge Hub — Reports Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#0f1117; color:#e2e8f0; font-family:'Segoe UI',sans-serif; }}
  .header {{ background:linear-gradient(135deg,#1a1f2e,#232b3e); padding:20px 30px; border-bottom:1px solid #2d3748; display:flex; justify-content:space-between; align-items:center; }}
  .header h1 {{ font-size:22px; color:#63b3ed; }}
  .header span {{ color:#718096; font-size:13px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px; padding:24px; }}
  .card {{ background:#1a1f2e; border-radius:12px; padding:20px; border:1px solid #2d3748; }}
  .card .label {{ color:#718096; font-size:12px; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px; }}
  .card .value {{ font-size:26px; font-weight:700; }}
  .card .sub {{ color:#718096; font-size:12px; margin-top:4px; }}
  .blue {{ color:#63b3ed; }} .green {{ color:#68d391; }} .yellow {{ color:#f6e05e; }} .purple {{ color:#b794f4; }} .red {{ color:#fc8181; }} .teal {{ color:#4fd1c5; }}
  .charts {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; padding:0 24px 24px; }}
  .chart-card {{ background:#1a1f2e; border-radius:12px; padding:20px; border:1px solid #2d3748; }}
  .chart-card h3 {{ color:#a0aec0; font-size:14px; margin-bottom:16px; }}
  .full {{ grid-column:1/-1; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ color:#718096; text-align:left; padding:8px; border-bottom:1px solid #2d3748; }}
  td {{ padding:8px; border-bottom:1px solid #1a1f2e; }}
  .footer {{ text-align:center; color:#4a5568; font-size:12px; padding:16px; }}
  @media(max-width:768px){{ .charts {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<div class="header">
  <h1>⬡ Bridge Hub — Reports Dashboard</h1>
  <span>განახლდა: {now}</span>
</div>

<div class="grid">
  <div class="card"><div class="label">ინვოისები</div><div class="value blue">{inv["cnt"]}</div><div class="sub">სულ: {inv_total:,.0f} ₾</div></div>
  <div class="card"><div class="label">ხარჯები</div><div class="value red">{exp["cnt"]}</div><div class="sub">სულ: {exp_total:,.0f} ₾</div></div>
  <div class="card"><div class="label">აქტიური კონტრაქტები</div><div class="value green">{cont["cnt"]}</div><div class="sub">ღირებ: {cont_total:,.0f} ₾</div></div>
  <div class="card"><div class="label">საბანკო ბალანსი</div><div class="value teal">{bank_total:,.0f} ₾</div><div class="sub">ყველა ანგარიში</div></div>
  <div class="card"><div class="label">შემოსავალი</div><div class="value yellow">{inc_total:,.0f} ₾</div><div class="sub">ჟურნალიდან</div></div>
  <div class="card"><div class="label">მოგება / ზარალი</div><div class="value {'green' if net >= 0 else 'red'}">{net:,.0f} ₾</div><div class="sub">{'▲ მოგება' if net >= 0 else '▼ ზარალი'}</div></div>
</div>

<div class="charts">
  <div class="chart-card">
    <h3>📊 ყოველთვიური ხარჯები 2026</h3>
    <canvas id="monthlyChart" height="200"></canvas>
  </div>
  <div class="chart-card">
    <h3>🥧 კონტრაქტები ტიპების მიხედვით</h3>
    <canvas id="contChart" height="200"></canvas>
  </div>
  <div class="chart-card full">
    <h3>📋 ბოლო Audit Events</h3>
    <table>
      <tr><th>Action</th><th>Actor</th><th>დრო</th></tr>
      {audit_rows if audit_rows else '<tr><td colspan="3" style="color:#4a5568">ჩანაწერი არ არის</td></tr>'}
    </table>
  </div>
</div>

<div class="footer">Bridge Hub v1.0.0 · Sprint 59 Complete · {now}</div>

<script>
new Chart(document.getElementById('monthlyChart'), {{
  type:'bar',
  data:{{
    labels:{monthly_labels},
    datasets:[{{label:'ხარჯი (₾)',data:{monthly_data},backgroundColor:'rgba(252,129,129,0.7)',borderRadius:6}}]
  }},
  options:{{plugins:{{legend:{{labels:{{color:'#a0aec0'}}}}}},scales:{{x:{{ticks:{{color:'#718096'}},grid:{{color:'#2d3748'}}}},y:{{ticks:{{color:'#718096'}},grid:{{color:'#2d3748'}}}}}}}}
}});
new Chart(document.getElementById('contChart'), {{
  type:'doughnut',
  data:{{
    labels:{cont_labels},
    datasets:[{{data:{cont_data},backgroundColor:['#63b3ed','#68d391','#f6e05e','#b794f4'],borderWidth:0}}]
  }},
  options:{{plugins:{{legend:{{position:'bottom',labels:{{color:'#a0aec0'}}}}}}}}
}});
</script>
</body>
</html>"""
    return HTMLResponse(content=html)
