#!/usr/bin/env bash
set -euo pipefail
PROD_URL="${1:?Usage: ./scripts/test_prod.sh https://prod-url}"
echo "== PROD /health =="; curl -i "$PROD_URL/health"
echo -e "\n== PROD /docs =="; curl -I "$PROD_URL/docs"
