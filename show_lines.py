c = open('app/api/services/ai_chat_service.py', 'r', encoding='utf-8').read()

# ვნახოთ ზუსტი კონტექსტი lines 425-460
lines = c.split('\n')
for i in range(424, 460):
    print(f'{i+1}: {repr(lines[i])}')
