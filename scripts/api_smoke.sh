#!/usr/bin/env bash
# Smoke-check the API from the terminal (health, auth, system, pages, keywords, tenders).
# Usage:
#   ./scripts/api_smoke.sh
#   API_BASE_URL=http://127.0.0.1:8000 SMOKE_EMAIL=you@preciseethiopia.com SMOKE_PASSWORD='secret' ./scripts/api_smoke.sh

set -euo pipefail

BASE="${API_BASE_URL:-http://localhost:8000}"
EMAIL="${SMOKE_EMAIL:-admin@preciseethiopia.com}"
PASS="${SMOKE_PASSWORD:-ChangeMe123!}"

say() { printf '\n=== %s ===\n' "$1"; }

curl_json() {
  local method="$1"
  local url="$2"
  shift 2
  curl -sS -X "$method" "$BASE$url" \
    -H "Content-Type: application/json" \
    "$@" \
    -w "\nHTTP %{http_code}\n"
}

say "Health (no auth)"
curl -sS "$BASE/health" -w "\nHTTP %{http_code}\n"

say "Login → bearer token"
LOGIN_BODY=$(printf '{"email":"%s","password":"%s"}' "$EMAIL" "$PASS")
RESP=$(curl -sS -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "$LOGIN_BODY") || true
TOKEN=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token') or '')") || true
if [[ -z "$TOKEN" ]]; then
  echo "Login failed. Raw response:"
  echo "$RESP"
  exit 1
fi
echo "Token acquired (${#TOKEN} chars)"

HDR_AUTH=( -H "Authorization: Bearer ${TOKEN}" )

say "GET /api/v1/auth/me"
curl -sS "$BASE/api/v1/auth/me" "${HDR_AUTH[@]}" -w "\nHTTP %{http_code}\n"

say "GET /api/v1/system/status"
curl -sS "$BASE/api/v1/system/status" "${HDR_AUTH[@]}" -w "\nHTTP %{http_code}\n"

say "GET /api/v1/system/email-settings"
curl -sS "$BASE/api/v1/system/email-settings" "${HDR_AUTH[@]}" -w "\nHTTP %{http_code}\n"

say "GET /api/v1/system/email-logs (limit 5)"
curl -sS "$BASE/api/v1/system/email-logs?limit=5" "${HDR_AUTH[@]}" -w "\nHTTP %{http_code}\n"

say "GET /api/v1/system/logs/crawl (limit 3)"
curl -sS "$BASE/api/v1/system/logs/crawl?limit=3" "${HDR_AUTH[@]}" -w "\nHTTP %{http_code}\n"

say "GET /api/v1/pages/"
curl -sS "$BASE/api/v1/pages/" "${HDR_AUTH[@]}" -w "\nHTTP %{http_code}\n"

say "GET /api/v1/keywords/"
curl -sS "$BASE/api/v1/keywords/" "${HDR_AUTH[@]}" -w "\nHTTP %{http_code}\n"

say "GET /api/v1/keywords/categories/stats"
curl -sS "$BASE/api/v1/keywords/categories/stats" "${HDR_AUTH[@]}" -w "\nHTTP %{http_code}\n"

say "GET /api/v1/tenders/"
curl -sS "$BASE/api/v1/tenders/" "${HDR_AUTH[@]}" -w "\nHTTP %{http_code}\n"

say "GET /api/v1/tenders/stats/summary"
curl -sS "$BASE/api/v1/tenders/stats/summary" "${HDR_AUTH[@]}" -w "\nHTTP %{http_code}\n"

say "Done. Optional one-offs (uncomment or run manually):"
cat <<'OPTIONAL'
# Crawler probe (can take a few seconds):
# curl -sS -X POST "$BASE/api/v1/system/test-crawler" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"url":"https://example.com"}'

# Screening test email (needs SMTP configured):
# curl -sS -X POST "$BASE/api/v1/system/test-email" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"email":"you@preciseethiopia.com","category":"screening_opportunities"}'
OPTIONAL
