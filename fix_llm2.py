with open("app/api/services/llm_service.py", "r", encoding="utf-8") as f:
    content = f.read()

old = '"შენ ხარ ქართული საბუღალტრო AI. დააბრუნე მხოლოდ JSON: {\\"account_code\\":\\"XXXX\\",\\"confidence\\":0.0,\\"reasoning\\":\\"\\"}"'
new = '"შენ ხარ ქართული საბუღალტრო AI. გაანალიზე ტრანზაქცია და დააბრუნე JSON ობიექტი. account_code უნდა იყოს რეალური 4-ნიშნა საბუღალტრო კოდი (7110=ხელფასი, 7130=კომუნალური, 7190=სხვა ხარჯი, 6100=შემოსავალი). confidence=0.0-1.0. reasoning=მოკლე ახსნა."'

if old in content:
    content = content.replace(old, new, 1)
    print("OK: prompt updated")
else:
    print("NOT FOUND - searching...")
    idx = content.find("XXXX")
    if idx > 0:
        print("Found XXXX at:", idx)
        print("Context:", repr(content[idx-100:idx+100]))

with open("app/api/services/llm_service.py", "w", encoding="utf-8") as f:
    f.write(content)
