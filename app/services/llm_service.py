import json
import os
from typing import Optional

async def llm_json(prompt: str, model: str = 'gpt-4o') -> dict:
    try:
        import openai
        client = openai.AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        resp = await client.chat.completions.create(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            response_format={'type': 'json_object'},
            temperature=0.1,
            max_tokens=1000,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return await llm_json_claude(prompt)

async def llm_json_claude(prompt: str) -> dict:
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        resp = await client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=1000,
            messages=[{'role': 'user', 'content': prompt + '\nReturn only valid JSON.'}],
        )
        text = resp.content[0].text
        text = text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except Exception as e:
        return {'error': str(e), 'confidence': 0.0}

async def llm_text(prompt: str, provider: str = 'claude') -> str:
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        resp = await client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=2000,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return resp.content[0].text
    except Exception as e:
        return f'Error: {str(e)}'

async def llm_extract(prompt: str) -> dict:
    return await llm_json(prompt)
