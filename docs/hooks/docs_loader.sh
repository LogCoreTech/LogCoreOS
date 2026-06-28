#!/bin/bash
# docs_loader.sh — LogCoreOS session start hook
# Injects core docs into context at the start of each session.
# Called via UserPromptSubmit hook in .claude/settings.json.
# Runs once per calendar day, then skips.

DOCS_DIR="/home/logcore/LogCoreDEV/LogCoreOS/docs"
SESSION_MARKER="/tmp/logcoreos_session_$(date +%Y%m%d)"

# Only inject on the first prompt of the day
if [ -f "$SESSION_MARKER" ]; then
  exit 0
fi
touch "$SESSION_MARKER"

TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)

read_file() {
  if [ -f "$1" ]; then cat "$1"; else echo "(not found: $1)"; fi
}

PENDING_FILE="/tmp/logcoreos_docs_pending"
PENDING_REMINDER=""
if [ -f "$PENDING_FILE" ]; then
  PENDING_REMINDER="
--- PENDING DOCS REMINDER (from last turn) ---
$(cat "$PENDING_FILE")
----------------------------------------------"
  rm -f "$PENDING_FILE"
fi

CONTEXT="=== LOGCOREOS — SESSION CONTEXT (auto-loaded) ===
You are the AI for LogCoreOS. Read the following before responding.
${PENDING_REMINDER}
--- SOUL.md ---
$(read_file "$DOCS_DIR/SOUL.md")

--- MEMORY.md ---
$(read_file "$DOCS_DIR/MEMORY.md")

--- TASKS.md ---
$(read_file "$DOCS_DIR/TASKS.md")

--- AGENTS.md ---
$(read_file "$DOCS_DIR/AGENTS.md")

--- Daily Note: $TODAY ---
$(read_file "$DOCS_DIR/Daily Notes/$TODAY.md")

--- Daily Note: $YESTERDAY ---
$(read_file "$DOCS_DIR/Daily Notes/$YESTERDAY.md")

=== END SESSION CONTEXT ==="

printf '%s' "$(jq -n --arg ctx "$CONTEXT" '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":$ctx}}')"
