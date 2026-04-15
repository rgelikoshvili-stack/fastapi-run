p = 'app/api/services/llm_service.py'

# utf-8-sig კითხულობს BOM-იან ფაილსაც სწორად
c = open(p, 'r', encoding='utf-8-sig').read()

# თავიდან BOM-ის გარეშე ვწერთ
with open(p, 'w', encoding='utf-8', newline='\n') as f:
    f.write(c)

print('BOM removed')
print(repr(open(p, 'r', encoding='utf-8').read()[:20]))
