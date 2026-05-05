#!/usr/bin/env bash
# Print eval-able exports for API_TOKEN / TOKEN (used by test_agent1_screening.sh).
# Usage:
#   API_LOGIN_EMAIL='you@example.com' API_LOGIN_PASSWORD='secret' eval "$(./scripts/login_token.sh)"
#
set -euo pipefail
BASE="${API_BASE_URL:-http://localhost:8000}"
EMAIL="${API_LOGIN_EMAIL:?Set API_LOGIN_EMAIL}"
PASS="${API_LOGIN_PASSWORD:?Set API_LOGIN_PASSWORD}"

BODY=$(printf '{"email":"%s","password":"%s"}' "$EMAIL" "$PASS")
RESP=$(curl -sS -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "$BODY") || true
TOKEN=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token') or '')") || true

if [[ -z "$TOKEN" ]]; then
  echo "login_token.sh: login failed" >&2
  echo "$RESP" >&2
  exit 1
fi

echo "export TOKEN='$TOKEN'"
echo "export API_TOKEN='$TOKEN'"
