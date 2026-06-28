#!/bin/bash
# safety_check.sh — PreToolUse hook: blocks destructive commands before they run
# Wired to the Bash tool via PreToolUse in .claude/settings.json

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

block() {
  printf '%s' "$(jq -n --arg reason "$1" '{"decision":"block","reason":$reason}')"
  exit 0
}

# Destructive git operations
if echo "$COMMAND" | grep -qE 'git\s+(push\s+.*(-f|--force)|reset\s+--hard|clean\s+-[a-z]*f[a-z]*|checkout\s+--\s*\.|restore\s+\.)'; then
  block "Destructive git command blocked: confirm with user before running this."
fi

# Recursive deletes
if echo "$COMMAND" | grep -qE 'rm\s+-[a-z]*r[a-z]*f[a-z]*|rm\s+-rf|rm\s+-fr'; then
  block "Recursive delete blocked: confirm with user before running this."
fi

# Destructive SQL
if echo "$COMMAND" | grep -qiE '(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE\s+TABLE)'; then
  block "Destructive SQL blocked: confirm with user before running this."
fi

# Force push variants
if echo "$COMMAND" | grep -qE 'git\s+push\s+.*--force-with-lease|git\s+push\s+--force'; then
  block "Force push blocked: confirm with user before running this."
fi

exit 0
