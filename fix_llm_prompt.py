with open("app/api/services/llm_service.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    'model\u0a are \u0e00\u0e07\u0e32\u0e23\u0e25\u0e35 \u0e2a\u0e32\u0e1a\u0e38\u0e0a\u0e32\u0e25\u0e35 AI. \u0e14\u0e32\u0e32\u0e1a\u0e23\u0e38\u0e19\u0e40 \u0e21\u0e02\u0e2d\u0e25\u0e2d\u0e14 JSON: {\\"account_code\\":\\"XXXX\\",\\"confidence\\":0.0,\\"reasoning\\":\\"\\"}',
    ""
)

old = '"შენ ხარ ქართული საბუღალტრო AI. დააბრუნე მხოლოდ JSON: {\\"account_code\\":\\"XXXX\\",\\"confidence\\":0.0,\\"reasoning\\":\\"\\"}"'
new = '"შენ ხარ ქართული საბუღალტრო AI. გაანალიზე ტრანზაქცია და დააბრუნე JSON: {\"account_code\":\"7130\",\"confidence\":0.85,\"reasoning\":\"კომუნალური ხარჯი\"}. account_code უნდა იყოს რეალური 4-ნიშნა კოდი (მაგ: 7110-7900, 6100, 1010)."'
content = content.replace(old, new, 1)

with open("app/api/services/llm_service.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!")
