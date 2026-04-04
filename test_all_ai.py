import os, json
# Load keys from .env
for line in open(".env").readlines():
    if "=" in line:
        k, v = line.strip().split("=", 1)
        os.environ[k] = v

transaction = {
    "description": "მაგთიკომი ინტერნეტი და მობილური მარტი 2026",
    "amount": 280.50,
    "partner": "Magticom Ltd"
}

print("=" * 60)
print("TRANSACTION:", transaction["description"])
print("AMOUNT:", transaction["amount"], "GEL")
print("=" * 60)

# 1. GPT-4o — კლასიფიკაცია
print("\n1. GPT-4o — კლასიფიკაცია:")
from openai import OpenAI
gpt = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
resp = gpt.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "შენ ხარ ქართული საბუღალტრო AI. დააბრუნე JSON: {\"account_code\":\"7130\",\"confidence\":0.95,\"reasoning\":\"კომუნალური\"}"},
        {"role": "user", "content": f"ტრანზაქცია: {transaction['description']}, თანხა: {transaction['amount']} GEL"}
    ],
    response_format={"type": "json_object"},
    temperature=0.1, max_tokens=200
)
gpt_result = json.loads(resp.choices[0].message.content)
print(f"   account_code: {gpt_result.get('account_code')}")
print(f"   confidence: {gpt_result.get('confidence')}")
print(f"   reasoning: {gpt_result.get('reasoning')}")

# 2. Claude — ახსნა
print("\n2. Claude — ბუღალტრული ახსნა:")
import anthropic
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
resp2 = claude.messages.create(
    model="claude-sonnet-4-6", max_tokens=150,
    messages=[{"role": "user", "content": f"გატარება: Dr{gpt_result.get('account_code')} Cr1010, {transaction['amount']} GEL — {transaction['description']}. ერთი მოკლე ქართული წინადადება."}]
)
print(f"   {resp2.content[0].text.strip()}")

# 3. Gemini — VAT ანალიზი
print("\n3. Gemini — VAT/საგადასახადო ანალიზი:")
from google import genai
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
resp3 = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=f"ქართული საბუღალტრო: {transaction['description']}, {transaction['amount']} GEL. VAT 18% გამოყოფა და PAYG 2% გათვლა. მოკლე ქართულად."
)
print(f"   {resp3.text.strip()}")

print("\n" + "=" * 60)
print("RESULT:")
print(f"  Account: {gpt_result.get('account_code')} (GPT-4o)")
print(f"  VAT: {round(transaction['amount'] * 0.18 / 1.18, 2)} GEL (Georgia Pack)")
print(f"  Net: {round(transaction['amount'] / 1.18, 2)} GEL")
print("=" * 60)
