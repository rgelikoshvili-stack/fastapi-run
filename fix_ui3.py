with open("static/approval.html", "r", encoding="utf-8") as f:
    content = f.read()

# fallback loop-დან ძველი paths ამოვიღოთ
content = content.replace(
    "'/approval/queue','/approvals/pending','/transactions/pending'",
    "'/approval/queue'"
)

with open("static/approval.html", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!")
