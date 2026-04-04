import app.api.services.llm_service as llm_service_test
import os
print("OPENAI KEY:", os.environ.get("OPENAI_API_KEY", "NOT SET")[:20])
try:
    r = llm_service_test.classify("ზღაპრული კომპანია", {}, "default")
    print("LLM result:", r)
except Exception as e:
    print("LLM ERROR:", e)
