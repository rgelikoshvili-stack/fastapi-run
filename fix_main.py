with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

old = "from app.api import routes_auth"
new = """from app.api import routes_auth
from app.api import routes_chat
from app.api import routes_1c
from app.api import routes_notifications
from app.api import routes_tax
from app.api import routes_search"""
content = content.replace(old, new, 1)

old2 = "app.include_router(routes_auth.router)"
new2 = """app.include_router(routes_auth.router)
app.include_router(routes_chat.router)
app.include_router(routes_1c.router)
app.include_router(routes_notifications.router)
app.include_router(routes_tax.router)
app.include_router(routes_search.router)"""
content = content.replace(old2, new2, 1)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!")
