c = open('app/api/services/llm_service.py', 'r', encoding='utf-8').read()
lines = c.split('\n')
for i in range(145, 165):
    print(f'{i+1}: {repr(lines[i])}')
