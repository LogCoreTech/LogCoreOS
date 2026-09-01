#!/bin/bash
# leak_check.sh — scans uncommitted changes (and the most recent commit, if it's
# new since this hook last ran) for real IP addresses and common secret patterns
# before they can reach the public repo. Wired as a Stop hook in .claude/settings.json.
#
# Enforces docs/MEMORY.md Security Rule 11: "No customer/tenant details in this
# repo — ever." Server IPs, SSH details, and account info belong only in the
# private Business repo. Added 2026-09-01 after two real IPs and a real client's
# name were found already committed and pushed to origin — see docs/MEMORY.md's
# 2026-08-31 entry for the full incident this hook exists to catch earlier next time.
#
# Advisory only — surfaces a reminder for Claude to review, never blocks anything.
# False positives (a version-looking string, a test fixture) are expected and fine;
# missing a real leak is the actual risk this exists to shrink.

REPO_DIR="/home/logcore/LogCoreOS"
[ -d "$REPO_DIR/.git" ] || REPO_DIR="/home/logcore/LogCoreDEV/LogCoreOS"
[ -d "$REPO_DIR/.git" ] || exit 0

cd "$REPO_DIR" || exit 0

STATE_FILE="/tmp/logcoreos_leak_check_state"
CURRENT_HEAD="$(git rev-parse HEAD 2>/dev/null)"
LAST_HEAD=""
[ -f "$STATE_FILE" ] && LAST_HEAD="$(cat "$STATE_FILE" 2>/dev/null)"

# What to scan: uncommitted changes to already-tracked files (working tree +
# staged, not yet committed — the actual "before committing" case), brand-new
# untracked files (git diff HEAD alone misses these entirely), plus the tip
# commit's own diff if it's new since the last time this hook ran (catches
# something that already landed in a commit this turn, before it's pushed).
DIFF="$(git diff HEAD -- . ':(exclude)docs/hooks/leak_check.sh' 2>/dev/null)"
if [ -n "$CURRENT_HEAD" ] && [ "$CURRENT_HEAD" != "$LAST_HEAD" ]; then
  DIFF="$DIFF
$(git show "$CURRENT_HEAD" -- . ':(exclude)docs/hooks/leak_check.sh' 2>/dev/null)"
fi
ADDED="$(echo "$DIFF" | grep -E '^\+[^+]')"

while IFS= read -r -d '' entry; do
  case "$entry" in
    '??'*) f="${entry:3}"
           [ -f "$f" ] && ADDED="$ADDED
$(sed 's/^/+/' "$f" 2>/dev/null)"
           ;;
  esac
done < <(git status --porcelain -z 2>/dev/null)

echo "$CURRENT_HEAD" > "$STATE_FILE" 2>/dev/null

[ -z "$ADDED" ] && exit 0

FINDINGS=""

# Real (non-private/non-reserved) IPv4 addresses.
IPS="$(echo "$ADDED" \
  | grep -oE '[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}' \
  | grep -vE '^(0\.|10\.|127\.|169\.254\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.|255\.255\.255\.255$)' \
  | sort -u)"
[ -n "$IPS" ] && FINDINGS="$FINDINGS
Possible real IP address(es): $(echo "$IPS" | tr '\n' ' ')"

# Common secret/key patterns.
if echo "$ADDED" | grep -qE 'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY'; then
  FINDINGS="$FINDINGS
A private key block"
fi
if echo "$ADDED" | grep -qE 'AKIA[0-9A-Z]{16}'; then
  FINDINGS="$FINDINGS
An AWS access key ID"
fi
SECRET_HITS="$(echo "$ADDED" \
  | grep -iE '(api[_-]?key|secret|token|password)[[:space:]]*[:=][[:space:]]*["'"'"'][A-Za-z0-9/+_-]{16,}["'"'"']' \
  | grep -viE 'change-me|your-key|xxx|placeholder|example')"
[ -n "$SECRET_HITS" ] && FINDINGS="$FINDINGS
A hardcoded-looking key/secret/token/password value"

[ -z "$FINDINGS" ] && exit 0

REMINDER="LEAK CHECK — $(date '+%Y-%m-%d %H:%M')
Possible sensitive data in uncommitted changes or the latest commit:
$FINDINGS

Review before committing/pushing. Security Rule 11 (docs/MEMORY.md): no customer/tenant
details (names, server IPs, hostnames, SSH info, account details) belong in this public
repo — only in the private Business repo, or nowhere written down at all. If this is a
false positive (a version string, test fixture, placeholder), ignore it."

printf '%s' "$(jq -n --arg ctx "$REMINDER" '{"hookSpecificOutput":{"hookEventName":"Stop","additionalContext":$ctx}}')"
