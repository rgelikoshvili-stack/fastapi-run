#!/usr/bin/env bash
set -euo pipefail

REGION="europe-west1"
SERVICE="fastapi-run-dev"

DEV_URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
TOKEN="$(gcloud auth print-identity-token)"

echo "=============================="
echo "DEV_URL=$DEV_URL"
echo "=============================="

echo
echo "== 1) /health =="
curl -s -H "Authorization: Bearer $TOKEN" "$DEV_URL/health" | python3 -m json.tool

echo
echo "== 2) /debug/openai =="
curl -s -H "Authorization: Bearer $TOKEN" "$DEV_URL/debug/openai" | python3 -m json.tool

echo
echo "== 3) /bridge/classify =="
RESP="$(curl -s -X POST "$DEV_URL/bridge/classify" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"Vendor: ACME LLC. Total: 120.00 GEL. VAT: 18% (VAT amount 18.31 GEL). Service: consulting. Date: 2026-02-20"}')"

echo "$RESP" | python3 -m json.tool

echo
echo "== 4) quick diagnosis =="
python3 - <<PY
import json
r=json.loads("""$RESP""")
res=r.get("result") or {}
err=str(res.get("llm_error") or "")
if "insufficient_quota" in err:
    print("❌ LLM ვერ მუშაობს: insufficient_quota (OpenAI billing/credits).")
else:
    print("✅ quota პრობლემა არ ჩანს.")
PY
