with open('app/api/routes_pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '    amount = amounts[0]["value"] if amounts else 0.0'
new = '    # ყველაზე დიდი თანხა ავიღოთ\n    amount = max((a["value"] for a in amounts), default=0.0) if amounts else 0.0'

if old in content:
    content = content.replace(old, new, 1)
    with open('app/api/routes_pipeline.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ Fixed!")
else:
    print("❌ Not found")
