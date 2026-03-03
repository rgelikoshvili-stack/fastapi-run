#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-https://fastapi-run-oobzrmikna-ew.a.run.app}"
echo "BASE=$BASE"

echo "== ROOT ==";   curl -sS "$BASE/" | head; echo
echo "== HEALTH =="; curl -sS "$BASE/health" | head; echo
echo "== OPENAPI =="; curl -sS "$BASE/openapi.json" | head -c 160; echo; echo

echo "== LEARN (teacher) =="
curl -sS -X POST "$BASE/bridge/learn" \
  -H "Content-Type: application/json" \
  -d '{
    "task_type":"classify",
    "input":{"locale":"ka","country":"GE","text":"ვაზისუბანში 125 ლარი საწვავი, ბარათით. მიმწოდებელი: Wissol"},
    "output":{"category":"FUEL","account_code":"7420","vat":{"rate":0.18}},
    "notes":"Fuel example teacher"
  }'
echo; echo

echo "== CLASSIFY =="
curl -sS -X POST "$BASE/bridge/classify" \
  -H "Content-Type: application/json" \
  -d '{"locale":"ka","country":"GE","text":"ვაზისუბანში 125 ლარი საწვავი, ბარათით. მიმწოდებელი: Wissol"}'
echo; echo

echo "== LOGS (debug) =="
curl -sS "$BASE/debug/log?limit=20" | head -c 1200; echo
echo
