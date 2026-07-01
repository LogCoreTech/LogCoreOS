#!/bin/bash
# docs_reminder.sh — smart end-of-turn docs update prompt.
# Fires on Stop. Detects what changed this turn and builds a targeted checklist.
# Only writes a pending reminder if no core docs were updated this turn.

DOCS_DIR="/home/logcore/LogCoreDEV/LogCoreOS/docs"
REPO_DIR="/home/logcore/LogCoreDEV/LogCoreOS"
PENDING_FILE="/tmp/logcoreos_docs_pending"
LAST_STOP_FILE="/tmp/logcoreos_last_stop"
MARKER="/tmp/logcoreos_stop_$(date +%Y%m%d_%H%M)"
TODAY=$(date +%Y-%m-%d)

# Only write once per minute to avoid looping
if [ -f "$MARKER" ]; then
  exit 0
fi
touch "$MARKER"
find /tmp -name "logcoreos_stop_*" -mmin +10 -delete 2>/dev/null

# Read last stop timestamp (0 = first ever run)
LAST_STOP=0
if [ -f "$LAST_STOP_FILE" ]; then
  LAST_STOP=$(cat "$LAST_STOP_FILE")
fi

# Check if any core docs were modified since the last stop
DOCS_UPDATED=false
if [ "$LAST_STOP" -gt 0 ]; then
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

# Skip reminder if core docs were already updated this turn
if [ "$DOCS_UPDATED" = "true" ]; then
  rm -f "$PENDING_FILE"
  exit 0
fi

# --- Detect what changed this turn ---
CHANGED_FILES=""
if [ "$LAST_STOP" -gt 0 ]; then
  REF_FILE=$(mktemp)
  python3 -c "import os; os.utime('$REF_FILE', ($LAST_STOP, $LAST_STOP))" 2>/dev/null
  CHANGED_FILES=$(find "$REPO_DIR/app" "$REPO_DIR/brain" "$REPO_DIR/docs/hooks" \
    -newer "$REF_FILE" -type f 2>/dev/null \
    | grep -vE "__pycache__|\.pyc|node_modules|/dist/|\.min\.")
  rm -f "$REF_FILE"
fi

# --- Build targeted checklist ---
CHECKLIST="1. docs/TASKS.md — mark completed tasks done; add new tasks surfaced this turn.
2. docs/MEMORY.md — update if design decisions or stable facts changed.
3. docs/Daily Notes/${TODAY}.md — update or create with what was worked on and decisions made."

ITEM_NUM=4
EXTRA=""

if [ -n "$CHANGED_FILES" ]; then
  # Untracked or newly staged app/ files → MAP.md (excludes docs/, daily notes, __pycache__, dist)
  NEW_FILES=$(git -C "$REPO_DIR" status --porcelain -z 2>/dev/null \
    | tr '\0' '\n' | grep -E "^\?\?|^A " \
    | sed 's/^.. //' | sed 's/^"\(.*\)"$/\1/' \
    | grep "^app/" \
    | grep -vE "__pycache__|\.pyc|/dist/|node_modules" | head -8)
  if [ -n "$NEW_FILES" ]; then
    NAMES=$(echo "$NEW_FILES" | sed 's|.*/||' | tr '\n' ' ' | sed 's/ $//')
    EXTRA="${EXTRA}
${ITEM_NUM}. docs/MAP.md — new app file(s): ${NAMES} — update the navigation index."
    ITEM_NUM=$((ITEM_NUM + 1))
  fi

  # Backend router changes → API.md
  ROUTER_CHANGES=$(echo "$CHANGED_FILES" | grep "app/backend/routers/" \
    | sed 's|.*/||' | grep -v "^_" | tr '\n' ' ' | sed 's/ $//')
  if [ -n "$ROUTER_CHANGES" ]; then
    EXTRA="${EXTRA}
${ITEM_NUM}. docs/API.md — router(s) changed: ${ROUTER_CHANGES} — update if new endpoints or signatures changed."
    ITEM_NUM=$((ITEM_NUM + 1))
  fi

  # config.py or main.py changes → MEMORY.md env vars / architecture
  if echo "$CHANGED_FILES" | grep -qE "app/backend/(main|config)\.py"; then
    EXTRA="${EXTRA}
${ITEM_NUM}. docs/MEMORY.md (env vars / architecture) — main.py or config.py changed; update Environment Variables table or Known Gotchas if anything non-obvious changed."
    ITEM_NUM=$((ITEM_NUM + 1))
  fi

  # scheduler.py changes → AGENTS.md scheduler table
  if echo "$CHANGED_FILES" | grep -q "app/backend/scheduler.py"; then
    EXTRA="${EXTRA}
${ITEM_NUM}. docs/AGENTS.md (Scheduler table) — scheduler.py changed; update the jobs table if new or modified jobs."
    ITEM_NUM=$((ITEM_NUM + 1))
  fi

  # New frontend pages → AGENTS.md pages list
  NEW_PAGES=$(echo "$CHANGED_FILES" | grep "app/frontend/src/pages/" \
    | sed 's|.*/||' | tr '\n' ' ' | sed 's/ $//')
  if [ -n "$NEW_PAGES" ]; then
    EXTRA="${EXTRA}
${ITEM_NUM}. docs/AGENTS.md (Frontend Conventions → Pages) — page file(s) changed: ${NEW_PAGES} — update the 17-page list if a page was added or renamed."
    ITEM_NUM=$((ITEM_NUM + 1))
  fi

  # Hook changes → AGENTS.md dev workflow
  HOOK_CHANGES=$(echo "$CHANGED_FILES" | grep "docs/hooks/" \
    | sed 's|.*/||' | tr '\n' ' ' | sed 's/ $//')
  if [ -n "$HOOK_CHANGES" ]; then
    EXTRA="${EXTRA}
${ITEM_NUM}. docs/AGENTS.md (Dev Skills / hook workflow) — hook(s) changed: ${HOOK_CHANGES} — update if the developer workflow or hook behavior changed."
    ITEM_NUM=$((ITEM_NUM + 1))
  fi

  # services/ changes that aren't covered above → MEMORY.md architecture
  SERVICE_CHANGES=$(echo "$CHANGED_FILES" | grep "app/backend/services/" \
    | sed 's|.*/||' | tr '\n' ' ' | sed 's/ $//')
  if [ -n "$SERVICE_CHANGES" ]; then
    EXTRA="${EXTRA}
${ITEM_NUM}. docs/MEMORY.md (Core Design Decisions) — service(s) changed: ${SERVICE_CHANGES} — update if any design decisions or invariants changed (atomic writes, auth, etc.)."
    ITEM_NUM=$((ITEM_NUM + 1))
  fi
fi

cat > "$PENDING_FILE" <<EOF
DOCS UPDATE REQUIRED — $(date '+%Y-%m-%d %H:%M')
No tracked docs were modified since the last stop. Update where applicable:

${CHECKLIST}${EXTRA}

SKIP all only if the last turn was pure Q&A — no files changed, no decisions made.
After updating (or deciding to skip), respond with one line: what you updated or 'Q&A only, skipped.'
EOF
