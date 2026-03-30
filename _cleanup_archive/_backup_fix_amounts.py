with open('app/api/doc_analyzer.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''def extract_amounts(text):
    out, seen = [], set()
    for m in re.finditer(AMOUNT_RE, text):
        s = m.group(1).strip().replace(" ","").replace(",","")
        try: val = float(s)
        except: continue
        if val == 0: continue
        cur = m.group(2)
        if cur == "₾": cur = "GEL"
        if cur == "$": cur = "USD"
        if cur == "€": cur = "EUR"
        k = (val, cur, m.group(0))
        if k in seen: continue
        seen.add(k)
        out.append({"raw": m.group(0), "value": val, "currency": cur})
    return out'''

new = '''def extract_amounts(text):
    out, seen = [], set()
    for m in re.finditer(AMOUNT_RE, text):
        s = m.group(1).strip().replace(" ","").replace(",","")
        try: val = float(s)
        except: continue
        if val == 0: continue
        # ID ნომრები გამოვრიცხოთ (10M+)
        if val >= 10000000: continue
        # წლები გამოვრიცხოთ (1900-2099)
        if 1900 <= val <= 2099: continue
        cur = m.group(2)
        if cur == "₾": cur = "GEL"
        if cur == "$": cur = "USD"
        if cur == "€": cur = "EUR"
        k = (val, cur, m.group(0))
        if k in seen: continue
        seen.add(k)
        out.append({"raw": m.group(0), "value": val, "currency": cur})
    return out'''

if old in content:
    content = content.replace(old, new, 1)
    with open('app/api/doc_analyzer.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ Fixed!")
else:
    print("❌ Not found - check function")
