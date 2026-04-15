c = open('app/api/services/ai_chat_service.py', 'r', encoding='utf-8').read()
lines = c.split('\n')

# lines 429-457 შევცვალოთ
old_block = '\n'.join(lines[428:457])
print('OLD BLOCK:')
print(repr(old_block))
