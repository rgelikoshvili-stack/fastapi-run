#!/usr/bin/env bash
set -euo pipefail
DEV_URL="${1:?Usage: ./scripts/test_dev.sh https://dev-url}"
TOKEN="$(gcloud auth print-identity-token)"
echo "== DEV /health (AUTH) =="; curl -i -H "Authorization: Bearer $TOKEN" "$DEV_URL/health"
echo -e "\n== DEV /docs (AUTH) =="; curl -I -H "Authorization: Bearer $TOKEN" "$DEV_URL/docs"
