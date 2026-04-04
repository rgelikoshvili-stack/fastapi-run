with open("static/approval.html", "r", encoding="utf-8") as f:
    content = f.read()

# find exact boundaries
start = content.find('<div style="margin-bottom:6px;display:flex;align-items:center;gap:8px;">')
end = content.find('<div class="chat-inp-wrap">', start)
print("START:", start, "END:", end)
print("CHUNK:", repr(content[start:end]))
