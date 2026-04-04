with open("static/approval.html", "r", encoding="utf-8") as f:
    content = f.read()

idx = content.find('class="chat-inp-area"')
print(repr(content[idx:idx+500]))
