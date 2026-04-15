p = 'app/api/services/llm_service.py'

c = open(p, 'r', encoding='utf-8-sig').read()

# ყველა BOM/non-printable FEFF მოვაშოროთ
c = c.replace('\ufeff', '')

with open(p, 'w', encoding='utf-8', newline='\n') as f:
    f.write(c)

print('ALL FEFF REMOVED')
print(repr(open(p, 'r', encoding='utf-8').read()[:40]))
