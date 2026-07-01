#!/bin/bash
# safety_check.sh — PreToolUse hook: blocks destructive commands before they run
# Wired to the Bash tool via PreToolUse in .claude/settings.json

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Strip heredoc bodies to avoid false positives from commit messages.
# Removes everything between <<'WORD' / <<"WORD" / <<WORD markers and the closing WORD line.
COMMAND=$(echo "$COMMAND" | awk '
  /<<['"'"'"]?[A-Z_]+['"'"'"]?/ {
    match($0, /<<['"'"'"]?([A-Z_]+)['"'"'"]?/, arr)
    delim = arr[1]
    in_hd = 1
    print
    next
  }
  in_hd && $0 == delim { in_hd = 0; print; next }
  in_hd { next }
  { print }
')

block() {
  printf '%s' "$(jq -n --arg reason "$1" '{"decision":"block","reason":$reason}')"
  exit 0
}

# Destructive git operations
if echo "$COMMAND" | grep -qE 'git\s+(push\s+.*(-f|--force)|reset\s+--hard|clean\s+-[a-z]*f[a-z]*|checkout\s+--\s*\.|restore\s+\.)'; then
  block "Destructive git command blocked: confirm with user before running this."
fi

# Force push variants
if echo "$COMMAND" | grep -qE 'git\s+push\s+.*--force-with-lease|git\s+push\s+--force'; then
  block "Force push blocked: confirm with user before running this."
fi

# Force branch delete
if echo "$COMMAND" | grep -qE 'git\s+branch\s+-[a-zA-Z]*D'; then
  block "Force branch delete blocked: confirm with user before running this."
fi

# Stash drop/clear
if echo "$COMMAND" | grep -qE 'git\s+stash\s+(drop|clear)'; then
  block "Stash drop/clear blocked: confirm with user before running this."
fi

# Recursive deletes
if echo "$COMMAND" | grep -qE 'rm\s+-[a-z]*r[a-z]*f[a-z]*|rm\s+-rf|rm\s+-fr'; then
  block "Recursive delete blocked: confirm with user before running this."
fi

# Destructive SQL
if echo "$COMMAND" | grep -qiE '(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE\s+TABLE)'; then
  block "Destructive SQL blocked: confirm with user before running this."
fi

exit 0
