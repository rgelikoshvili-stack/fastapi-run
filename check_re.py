c = open('app/api/services/llm_service.py', 'r', encoding='utf-8').read()

# ვამოწმოთ import re არის თუ არა
print('has import re:', 'import re' in c)
print('first 5 lines:')
for l in c.split('\n')[:5]:
    print(repr(l))
