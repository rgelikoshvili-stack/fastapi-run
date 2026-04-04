with open("static/approval.html", "r", encoding="utf-8") as f:
    content = f.read()
changes = 0
for old, new in [
    ("method, headers: {'Content-Type':'application/json'},",
     "method, headers: {'Content-Type':'application/json','X-Tenant-ID':TENANT_ID},"),
    ("method:'POST', headers:{'Content-Type':'application/json'},",
     "method:'POST', headers:{'Content-Type':'application/json','X-Tenant-ID':TENANT_ID},"),
]:
    if old in content:
        content = content.replace(old, new); changes += 1; print("OK: " + old[:30])
with open("static/approval.html", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!", changes, "changes")
