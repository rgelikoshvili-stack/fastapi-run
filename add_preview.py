# -*- coding: utf-8 -*-
with open('static/approval.html', 'r', encoding='utf-8') as f:
    content = f.read()

# attachment სიაში "👁 ნახვა" ღილაკის დამატება
old_att = """${atts.map(a=>`<span style="background:#fff;border:1px solid var(--gray-200);border-radius:6px;padding:4px 8px;font-size:11px;">📎 ${a.filename} (${Math.round(a.size/1024)}KB)</span>`).join('')}"""

new_att = """${atts.map(a=>`<span style="display:inline-flex;align-items:center;gap:6px;background:#fff;border:1px solid var(--gray-200);border-radius:6px;padding:4px 8px;font-size:11px;">📎 ${a.filename} (${Math.round(a.size/1024)}KB)<a href="${BASE}/email-invoice/preview/${em.message_id}/${encodeURIComponent(a.filename)}" target="_blank" style="color:var(--blue);font-weight:700;text-decoration:none;">👁 ნახვა</a></span>`).join('')}"""

if old_att in content:
    content = content.replace(old_att, new_att)
    print("Preview button added!")
else:
    print("ERROR: pattern not found")

with open('static/approval.html', 'w', encoding='utf-8') as f:
    f.write(content)
