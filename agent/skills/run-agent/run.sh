#!/usr/bin/env bash
# run-agent — send a goal to the LogCore AI agent and print the result
set -euo pipefail

GOAL="${1:?Usage: $0 \"goal\" [BASE_URL] [TOKEN]}"
BASE="${2:-http://localhost:8000/api}"
TOKEN="${3:-${LOGCORE_TOKEN:-}}"

if [[ -z "$TOKEN" ]]; then
  echo "Error: TOKEN argument or LOGCORE_TOKEN env var required" >&2
  exit 1
fi

PAYLOAD=$(jq -n --arg msg "$GOAL" '{"message": $msg, "history": []}')

RESPONSE=$(curl -sf \
  -X POST "$BASE/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "$PAYLOAD")

MODE=$(echo "$RESPONSE" | jq -r '.mode // "unknown"')
ANSWER=$(echo "$RESPONSE" | jq -r '.response // ""')
STEPS=$(echo "$RESPONSE" | jq -c '.steps // []')

echo ""
echo "[$MODE]"
echo ""
echo "$ANSWER"

TOOL_COUNT=$(echo "$STEPS" | jq '[.[] | select(.type == "tool_call")] | length')
if [[ "$TOOL_COUNT" -gt 0 ]]; then
  echo ""
  echo "--- Actions taken ($TOOL_COUNT) ---"
  echo "$STEPS" | jq -r '.[] | select(.type == "tool_call") |
    "• \(.tool)(\(.input | tojson | .[0:80]))\n  → \(.output | tojson | .[0:120])"'
fi
