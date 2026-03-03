from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/", response_class=HTMLResponse)
def dashboard():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Bridge Hub Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; background: #1a1a2e; color: #eee; }
        .header { background: #16213e; padding: 20px 40px; display: flex; align-items: center; }
        .header h1 { margin: 0; color: #0f3460; color: #e94560; font-size: 24px; }
        .container { padding: 30px 40px; }
        .cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }
        .card { background: #16213e; border-radius: 10px; padding: 20px; text-align: center; }
        .card h2 { font-size: 36px; margin: 0; color: #e94560; }
        .card p { margin: 5px 0 0; color: #aaa; font-size: 14px; }
        .section { background: #16213e; border-radius: 10px; padding: 20px; margin-bottom: 20px; }
        .section h3 { margin-top: 0; color: #e94560; }
        .status { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; }
        .ok { background: #0d7377; } .warn { background: #e94560; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #0f3460; font-size: 14px; }
        th { color: #e94560; }
        .refresh { float: right; background: #e94560; color: white; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer; }
    </style>
</head>
<body>
<div class="header">
    <h1>🏦 Bridge Hub + GAAS v5.2</h1>
    <button class="refresh" onclick="loadData()">↻ Refresh</button>
</div>
<div class="container">
    <div class="cards">
        <div class="card"><h2 id="journal-count">...</h2><p>Journal Entries</p></div>
        <div class="card"><h2 id="issues-count">...</h2><p>Audit Issues</p></div>
        <div class="card"><h2 id="users-count">...</h2><p>Users</p></div>
        <div class="card"><h2 id="keys-count">...</h2><p>API Keys</p></div>
    </div>
    <div class="section">
        <h3>System Status</h3>
        <span class="status ok" id="status">● Checking...</span>
    </div>
    <div class="section">
        <h3>Recent Journal Entries</h3>
        <table><thead><tr><th>ID</th><th>Description</th><th>Amount</th><th>Status</th></tr></thead>
        <tbody id="journal-table"><tr><td colspan="4">Loading...</td></tr></tbody></table>
    </div>
</div>
<script>
async function loadData() {
    try {
        const h = await fetch('/health');
        const hd = await h.json();
        document.getElementById('status').innerHTML = '● ' + hd.service + ' v' + hd.version;
        document.getElementById('status').className = 'status ok';
    } catch(e) { document.getElementById('status').innerHTML = '● Offline'; document.getElementById('status').className = 'status warn'; }
    
    try {
        const j = await fetch('/accounting/journal/list');
        const jd = await j.json();
        const entries = jd.entries || jd || [];
        document.getElementById('journal-count').innerText = entries.length;
        const tbody = document.getElementById('journal-table');
        tbody.innerHTML = entries.slice(0,5).map(e => 
            '<tr><td>' + (e.id||'').toString().slice(0,8) + '...</td><td>' + (e.description||e.memo||'-') + '</td><td>' + (e.amount||'-') + '</td><td><span class="status ok">posted</span></td></tr>'
        ).join('') || '<tr><td colspan="4">No entries</td></tr>';
    } catch(e) { document.getElementById('journal-count').innerText = '?'; }

    try {
        const u = await fetch('/users/');
        const ud = await u.json();
        document.getElementById('users-count').innerText = ud.length;
    } catch(e) { document.getElementById('users-count').innerText = '?'; }

    try {
        const k = await fetch('/auth/keys');
        const kd = await k.json();
        document.getElementById('keys-count').innerText = (kd.keys||kd||[]).length;
    } catch(e) { document.getElementById('keys-count').innerText = '?'; }

    try {
        const i = await fetch('/audit/issues');
        const id = await i.json();
        document.getElementById('issues-count').innerText = (id.issues||id||[]).length;
    } catch(e) { document.getElementById('issues-count').innerText = '?'; }
}
loadData();
</script>
</body>
</html>
"""