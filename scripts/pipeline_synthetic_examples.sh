#!/usr/bin/env bash
# Examples: POST /api/v1/system/test-pipeline-synthetic with different page names & URLs.
#
# 1) Export a JWT (required — system routes use auth):
#    export TOKEN=$(curl -sS -X POST "${API_BASE_URL:-http://localhost:8000}/api/v1/auth/login" \
#      -H "Content-Type: application/json" \
#      -d '{"email":"YOU@preciseethiopia.com","password":"YOUR_PASSWORD"}' \
#      | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
#
# 2) Run one block or the whole file:
#    bash scripts/pipeline_synthetic_examples.sh
#
set -euo pipefail

BASE="${API_BASE_URL:-http://localhost:8000}"
RECIPIENT="${SYNTH_RECIPIENT:-surafel@preciseethiopia.com}"

if [[ -z "${TOKEN:-}" ]]; then
  echo "Set TOKEN first (see comments at top of this script)." >&2
  exit 1
fi

AUTH=( -H "Authorization: Bearer ${TOKEN}" )

post_synthetic() {
  local name="$1" url="$2" run="$3" extra_json="${4:-}"
  # extra_json optional: comma-prefixed fragments e.g. ', "deadline_override": "2026-06-01"'
  curl -sS -X POST "${BASE}/api/v1/system/test-pipeline-synthetic" \
    -H "accept: application/json" \
    -H "Content-Type: application/json" \
    "${AUTH[@]}" \
    -d "{\"recipient_email\":\"${RECIPIENT}\",\"page_name\":\"${name}\",\"synthetic_page_url\":\"${url}\",\"run_id\":\"${run}\"${extra_json}}"
  echo ""
}

echo "--- Run A: EU-style name + distinct synthetic URL ---"
post_synthetic \
  "EU Funding Portal Demo" \
  "https://example.com/pipeline-test/eu-funding-demo" \
  "run-eu-001" \
  ', "send_emails": false'

echo "--- Run B: USAID-style label + another URL ---"
post_synthetic \
  "USAID Opportunity Monitor (test)" \
  "https://example.com/pipeline-test/usaid-monitor" \
  "run-usaid-002" \
  ', "send_emails": false'

echo "--- Run C: Merkato-style + deadline override ---"
post_synthetic \
  "Merkato Tender Sandbox" \
  "https://example.com/pipeline-test/merkato-sandbox" \
  "run-merkato-003" \
  ', "deadline_override": "2026-09-30", "send_emails": false'

echo "--- Run D: RFX / World Bank style + send_emails true (needs SMTP) ---"
post_synthetic \
  "RFX Now Screening Dry Run" \
  "https://example.com/pipeline-test/rfxnow-sample" \
  "run-rfx-004" \
  ', "deadline_override": "2026-08-15", "send_emails": true'

echo "Done."
