with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()
changes = 0
old = "from app.api import routes_erp_connectors"
new = "from app.api import routes_erp_connectors\nfrom app.api import routes_auth"
if old in content:
    content = content.replace(old, new, 1); changes += 1; print("OK: import routes_auth")
old2 = "app.include_router(routes_erp_connectors.router)"
new2 = "app.include_router(routes_erp_connectors.router)\napp.include_router(routes_auth.router)"
if old2 in content:
    content = content.replace(old2, new2, 1); changes += 1; print("OK: include routes_auth")
with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!", changes, "changes")
