with open("static/approval.html", "r", encoding="utf-8") as f:
    content = f.read()
changes = 0
old = "const BASE = 'http://127.0.0.1:8000';"
new = "const BASE = 'http://127.0.0.1:8000';\nlet TENANT_ID = localStorage.getItem('tenant_id') || 'default';"
if old in content:
    content = content.replace(old, new, 1); changes += 1; print("OK: TENANT_ID")
for old2, new2 in [("method, headers:{'Content-Type':'application/json'},","method, headers:{'Content-Type':'application/json','X-Tenant-ID':TENANT_ID},"),("method, headers: {'Content-Type': 'application/json'},","method, headers: {'Content-Type': 'application/json', 'X-Tenant-ID': TENANT_ID},")]:
    if old2 in content:
        content = content.replace(old2, new2, 1); changes += 1; print("OK: X-Tenant-ID"); break
old3 = '<button class="btn-header" onclick="refreshCurrent()">'
new3 = '<select id="tenantSel" onchange="changeTenant(this.value)" style="padding:7px 12px;border:1px solid var(--border2);border-radius:6px;font-size:13px;background:var(--surface3);cursor:pointer;margin-right:8px;"><option value="default">default</option></select>\n  <button class="btn-header" onclick="refreshCurrent()">'
if old3 in content:
    content = content.replace(old3, new3, 1); changes += 1; print("OK: tenant selector")
inject = "\nfunction changeTenant(val){TENANT_ID=val;localStorage.setItem('tenant_id',val);refreshCurrent();}\nfunction fmtAnomaly(row){if(!row.anomaly_flag)return '';return '<span style=\"color:#dc2626;font-weight:700;\">\u26a8 ANOMALY</span>';}\nfunction fmtVat(row){const vi=row.vat_info||{};if(!vi.suggested&&!row.vat_suggested)return '';return '<span style=\"font-size:11px;background:#dbeafe;color:#1d4ed8;padding:2px 6px;border-radius:4px;\">VAT '+(vi.amount||row.vat_amount||'')+'</span>';}\n"
if 'function buildTable(' in content:
    content = content.replace('function buildTable(', inject+'function buildTable(', 1); changes += 1; print("OK: helpers")
old5 = "    const id = getId(row);"
new5 = "    const id = getId(row);\n    const anomalyBadge = fmtAnomaly(row);\n    const vatBadge = fmtVat(row);\n    const expl = row.explanation ? '<div style=\"font-size:11px;color:#64748b;\">' + row.explanation + '</div>' : '';"
if old5 in content:
    content = content.replace(old5, new5, 1); changes += 1; print("OK: buildTable row")
with open("static/approval.html", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!", changes, "changes")
