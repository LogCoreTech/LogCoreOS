#!/bin/bash
# docs_loader.sh — LogCoreOS session context hook
# Injects SOUL.md inline and instructs Claude to read the other core docs.
# Called via UserPromptSubmit hook in .claude/settings.json on every prompt.

DOCS_DIR="/home/logcore/LogCoreDEV/LogCoreOS/docs"
TODAY=$(date +%Y-%m-%d)

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

# Build daily note read list — today's note always included, plus most recent previous note
DAILY_READ="- $DOCS_DIR/Daily Notes/$TODAY.md"
PREV_NOTE=$(ls -t "$DOCS_DIR/Daily Notes/"*.md 2>/dev/null | grep -v "$TODAY.md" | head -1)
if [ -n "$PREV_NOTE" ]; then
  DAILY_READ="$DAILY_READ
- $PREV_NOTE"
fi

CONTEXT="=== LOGCOREOS — SESSION CONTEXT ===
You are the AI for LogCoreOS.
${PENDING_REMINDER}
--- SOUL.md ---
$(read_file "$DOCS_DIR/SOUL.md")
--- END SOUL.md ---

REQUIRED — before responding, use the Read tool to read these files:
- $DOCS_DIR/AGENTS.md
- $DOCS_DIR/MEMORY.md
- $DOCS_DIR/TASKS.md
$DAILY_READ

Read all of them, then respond to the user's message.
=== END SESSION CONTEXT ==="

printf '%s' "$(jq -n --arg ctx "$CONTEXT" '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":$ctx}}')"
