with open("app/api/services/llm_service.py", "r", encoding="utf-8") as f:
    content = f.read()

idx = content.find("genai.GenerativeModel")
chunk = content[idx-200:idx+300]
print(repr(chunk))
