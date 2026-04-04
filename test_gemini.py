import os
os.environ["GEMINI_API_KEY"] = open(".env").read().split("GEMINI_API_KEY=")[1].split("\n")[0].strip()

from google import genai
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
resp = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="გამარჯობა! ქართულად 1 წინადადება."
)
print("Gemini:", resp.text)
