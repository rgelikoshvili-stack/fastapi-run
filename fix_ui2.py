with open("static/approval.html", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("api('/learning/status')", "api('/learning/health')")
content = content.replace("url:'/approvals/pending'", "url:'/approval/queue'")

with open("static/approval.html", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!")
