#!/usr/bin/env bash
# Call POST /api/v1/system/test-agent1-screening with a bundled markdown fixture (real LLM).
#
# Prerequisites:
#   - API server running (e.g. uvicorn)
#   - jq installed
#   - A real login email/password (not Unicode ellipsis …)
#
# Usage:
#   API_LOGIN_EMAIL='admin@preciseethiopia.com' API_LOGIN_PASSWORD='YourPassword' \
#     ./scripts/test_agent1_screening.sh strong
#
# If you see {"detail":"Could not validate credentials"}, your shell may still have an old
# TOKEN exported (wrong SECRET_KEY / expired). This script always re-logins when email+password
# are set; use TOKEN alone only when you omit credentials.
#
# Tiers: zero | low | strong | strong-fr  (fixtures under tests/fixtures/agent1_screening/)
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${API_BASE_URL:-http://localhost:8000}"
TIER="${1:-strong}"

case "$TIER" in
  zero|low|strong) ;;
  strong-fr|strong_fr|french) TIER="strong-fr" ;;
  *)
    echo "Usage: $0 {zero|low|strong|strong-fr}" >&2
    exit 1
    ;;
esac

if [[ "$TIER" == "strong-fr" ]]; then
  FIXTURE="$ROOT/tests/fixtures/agent1_screening/strong_match_notice_fr.md"
else
  FIXTURE="$ROOT/tests/fixtures/agent1_screening/${TIER}_match_notice.md"
fi
if [[ ! -f "$FIXTURE" ]]; then
  echo "Fixture not found: $FIXTURE" >&2
  exit 1
fi

# Prefer fresh login whenever credentials are passed — a leftover TOKEN in the environment
# would otherwise skip login and trigger 401 "Could not validate credentials" on the API call.
if [[ -n "${API_LOGIN_EMAIL:-}" && -n "${API_LOGIN_PASSWORD:-}" ]]; then
  # shellcheck disable=SC1090
  eval "$("$ROOT/scripts/login_token.sh")"
elif [[ -z "${TOKEN:-}" ]]; then
  echo "Either export TOKEN, or set API_LOGIN_EMAIL and API_LOGIN_PASSWORD (real email with @)." >&2
  exit 1
fi

BODY=$(jq -n \
  --rawfile content "$FIXTURE" \
  --arg url "https://fixture.example/agent1-screening/${TIER}" \
  '{page_content: $content, page_url: $url}')

curl -sS -X POST "${BASE}/api/v1/system/test-agent1-screening" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$BODY" | jq .
