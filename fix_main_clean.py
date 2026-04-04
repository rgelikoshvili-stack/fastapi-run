with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# ყველა balance_ge import/router ამოვიღოთ და ერთხელ დავამატოთ
import re
content = re.sub(r'from app\.api import routes_balance_ge\n', '', content)
content = re.sub(r'app\.include_router\(routes_balance_ge\.router\)\n', '', content)
content = re.sub(r'# from app\.api import routes_balance_ge\n', '', content)

# ერთხელ დავამატოთ
content = content.replace(
    "from app.api import routes_auth\n",
    "from app.api import routes_auth\nfrom app.api import routes_balance_ge\n",
    1
)
content = content.replace(
    "app.include_router(routes_auth.router)\n",
    "app.include_router(routes_auth.router)\napp.include_router(routes_balance_ge.router)\n",
    1
)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!")
