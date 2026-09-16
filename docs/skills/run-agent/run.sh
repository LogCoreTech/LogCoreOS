#!/usr/bin/env bash
# run-agent — send a goal to the LogCore AI agent and print the result
set -euo pipefail

GOAL="${1:?Usage: $0 \"goal\" [BASE_URL] [TOKEN]}"
BASE="${2:-http://localhost:8000/api/v1}"
TOKEN="${3:-${LOGCORE_TOKEN:-}}"

if [[ -z "$TOKEN" ]]; then
  echo "Error: TOKEN argument or LOGCORE_TOKEN env var required" >&2
  echo "  Get one with: curl -s -X POST \$BASE/auth/token -H 'Content-Type: application/json' \\" >&2
  echo "                  -d '{\"email\":\"you@example.com\",\"password\":\"...\"}' | jq -r '.token'" >&2
  exit 1
fi

# chat_id is required on every POST /chat since 2026-08-15 (ChatRequest.chat_id) — a fresh
# one per invocation is fine here since this script never preserves history across calls anyway.
CHAT_ID=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || uuidgen 2>/dev/null || python3 -c 'import uuid; print(uuid.uuid4())')

PAYLOAD=$(jq -n --arg msg "$GOAL" --arg chat_id "$CHAT_ID" '{"message": $msg, "history": [], "chat_id": $chat_id}')

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
