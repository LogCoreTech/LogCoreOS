#!/bin/bash
# docs_reminder.sh — LogCoreOS end-of-turn docs update reminder.
# Fires on Stop. Skips if any tracked doc was modified since the last stop.
# Writes a pending reminder to a file; docs_loader.sh picks it up on the
# next UserPromptSubmit and injects it as context.

DOCS_DIR="/home/logcore/LogCoreDEV/LogCoreOS/docs"
PENDING_FILE="/tmp/logcoreos_docs_pending"
LAST_STOP_FILE="/tmp/logcoreos_last_stop"
MARKER="/tmp/logcoreos_stop_$(date +%Y%m%d_%H%M)"
TODAY=$(date +%Y-%m-%d)

# Only write once per minute to avoid looping
if [ -f "$MARKER" ]; then
  exit 0
fi
touch "$MARKER"

# Clean up old markers
find /tmp -name "logcoreos_stop_*" -mmin +10 -delete 2>/dev/null

# Check if any tracked docs were modified since the last stop
DOCS_UPDATED=false
if [ -f "$LAST_STOP_FILE" ]; then
  LAST_STOP=$(cat "$LAST_STOP_FILE")
  for f in "$DOCS_DIR/TASKS.md" "$DOCS_DIR/MEMORY.md" "$DOCS_DIR/Daily Notes/$TODAY.md"; do
    if [ -f "$f" ]; then
      FILE_MTIME=$(stat -c %Y "$f")
      if [ "$FILE_MTIME" -gt "$LAST_STOP" ]; then
        DOCS_UPDATED=true
        break
      fi
    fi
  done
fi

# Record current stop time for next comparison
date +%s > "$LAST_STOP_FILE"

# Skip reminder if docs were updated this turn
if [ "$DOCS_UPDATED" = "true" ]; then
  exit 0
fi

cat > "$PENDING_FILE" <<EOF
DOCS UPDATE REQUIRED — $(date '+%Y-%m-%d %H:%M')
You stopped last turn without confirming docs were updated. Check each item:

1. docs/TASKS.md — mark completed tasks done; add new tasks surfaced this turn.
2. docs/MEMORY.md — update if design decisions or stable facts changed.
3. docs/Daily Notes/${TODAY}.md — update or create if real work was done this turn.

SKIP all three only if the last turn was pure Q&A with no files changed and no decisions made.
After updating (or deciding to skip), respond with one line: what you updated or 'Q&A only, skipped.'
EOF
