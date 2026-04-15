c = open('app/api/services/ai_chat_service.py', 'r', encoding='utf-8').read()

# ვნახოთ LLM fallback ადგილი
lines = c.split('\n')
for i,l in enumerate(lines):
    if 'llm_classify' in l or 'llm_result' in l or 'generate_preview' in l:
        print(f'{i+1}: {repr(l)}')
