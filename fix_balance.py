with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    "from app.api import routes_auth",
    "from app.api import routes_auth\nfrom app.api import routes_balance_ge"
)
content = content.replace(
    "app.include_router(routes_auth.router)",
    "app.include_router(routes_auth.router)\napp.include_router(routes_balance_ge.router)"
)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!")
