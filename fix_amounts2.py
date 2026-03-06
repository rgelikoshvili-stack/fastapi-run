with open('app/api/doc_analyzer.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '        # ID ნომრები გამოვრიცხოთ (10M+)\n        if val >= 10000000: continue\n        # წლები გამოვრიცხოთ (1900-2099)\n        if 1900 <= val <= 2099: continue'

new = '        # ID ნომრები გამოვრიცხოთ (10M+)\n        if val >= 10000000: continue\n        # წლები გამოვრიცხოთ (1900-2099)\n        if 1900 <= val <= 2099: continue\n        # პატარა რიცხვები გამოვრიცხოთ (< 10)\n        if val < 10: continue'

if old in content:
    content = content.replace(old, new, 1)
    with open('app/api/doc_analyzer.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ Fixed!")
else:
    print("❌ Not found")
