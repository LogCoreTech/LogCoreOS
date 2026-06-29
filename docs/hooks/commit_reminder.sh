#!/bin/bash
# commit_reminder.sh — fires every 30 minutes if there are uncommitted changes
# Wired as a Stop hook in .claude/settings.json

REPO_DIR="/home/logcore/LogCoreDEV/LogCoreOS"
# Marker changes every 30 minutes (YYYYMMDD_HHMM where MM is floored to 00 or 30)
MINUTE=$(date +%M)
HALF=$(( MINUTE < 30 ? 0 : 30 ))
MARKER="/tmp/logcoreos_commit_$(date +%Y%m%d_%H)$(printf '%02d' $HALF)"

if [ -f "$MARKER" ]; then
  exit 0
fi
touch "$MARKER"

# Clean up old markers
find /tmp -name "logcoreos_commit_*" -mmin +60 -delete 2>/dev/null

# Only remind if there are actual changes
if git -C "$REPO_DIR" status --porcelain | grep -q .; then
  CHANGED=$(git -C "$REPO_DIR" status --porcelain | wc -l | tr -d ' ')
  REMINDER="COMMIT REMINDER — $(date '+%Y-%m-%d %H:%M')
There are $CHANGED uncommitted change(s) in LogCoreOS. Consider committing to master if the current work is at a stable point.

To commit:
  git add -p
  git commit -m \"feat: ...\"
  GIT_SSH_COMMAND=\"ssh -i /home/logcore/.ssh/logcore_github\" git push origin master

Skip if work is still in progress."

  printf '%s' "$(jq -n --arg ctx "$REMINDER" '{"hookSpecificOutput":{"hookEventName":"Stop","additionalContext":$ctx}}')"
fi
