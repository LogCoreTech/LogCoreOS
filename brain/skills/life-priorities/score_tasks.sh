#!/usr/bin/env bash
# score_tasks.sh — Score and rank a user's tasks by life priority
# Usage: bash score_tasks.sh "User Name"
# Requires: jq

set -euo pipefail

BRAIN_PATH="$(cd "$(dirname "$0")/../.." && pwd)"
USER_NAME="${1:?Usage: score_tasks.sh \"User Name\"}"
TASKS_FILE="$BRAIN_PATH/USERS/$USER_NAME/Tasks/tasks.json"
PROFILE_FILE="$BRAIN_PATH/USERS/$USER_NAME/Profile.md"
OVERRIDE_FILE="$BRAIN_PATH/USERS/$USER_NAME/Tasks/daily_override.json"
TODAY=$(date +%Y-%m-%d)
THIS_WEEK=$(date -d "+7 days" +%Y-%m-%d 2>/dev/null || date -v+7d +%Y-%m-%d)

if [[ ! -f "$TASKS_FILE" ]]; then
  echo "No tasks file found at: $TASKS_FILE" && exit 1
fi

# --- Build priority order ---
PRIORITY_ORDER=()

# Check daily override first
if [[ -f "$OVERRIDE_FILE" ]]; then
  override_date=$(jq -r '.date' "$OVERRIDE_FILE")
  if [[ "$override_date" == "$TODAY" ]]; then
    mapfile -t PRIORITY_ORDER < <(jq -r '.order[]' "$OVERRIDE_FILE")
  fi
fi

# Fall back to profile order if override not active
if [[ ${#PRIORITY_ORDER[@]} -eq 0 ]]; then
  # Extract numbered list from ## Life Priorities section of Profile.md
  in_section=false
  while IFS= read -r line; do
    if [[ "$line" == "## Life Priorities" ]]; then
      in_section=true
      continue
    fi
    if [[ "$in_section" == true ]]; then
      if [[ "$line" =~ ^##[[:space:]] ]]; then break; fi
      if [[ "$line" =~ ^[0-9]+\.[[:space:]](.+)$ ]]; then
        PRIORITY_ORDER+=("${BASH_REMATCH[1]}")
      fi
    fi
  done < "$PROFILE_FILE"
fi

TOTAL_CATS=${#PRIORITY_ORDER[@]}

# --- Score each pending task ---
SCORED=$(jq --argjson today "\"$TODAY\"" --argjson week "\"$THIS_WEEK\"" '
  .tasks[] | select(.status == "pending")
' "$TASKS_FILE" | jq -s '.')

output=""
while IFS= read -r task_json; do
  title=$(echo "$task_json" | jq -r '.title')
  category=$(echo "$task_json" | jq -r '.category')
  priority=$(echo "$task_json" | jq -r '.priority')
  due_date=$(echo "$task_json" | jq -r '.due_date // empty')
  streak=$(echo "$task_json" | jq -r '.streak_count // 0')

  # Category weight
  cat_weight=1
  for i in "${!PRIORITY_ORDER[@]}"; do
    if [[ "${PRIORITY_ORDER[$i]}" == "$category" ]]; then
      cat_weight=$(( TOTAL_CATS - i ))
      break
    fi
  done

  # Priority weight
  case "$priority" in
    High)   pri_weight=3 ;;
    Medium) pri_weight=2 ;;
    *)      pri_weight=1 ;;
  esac

  # Urgency bonus
  urgency=0
  if [[ -n "$due_date" ]]; then
    if [[ "$due_date" < "$TODAY" ]]; then urgency=10
    elif [[ "$due_date" == "$TODAY" ]]; then urgency=5
    elif [[ "$due_date" < "$THIS_WEEK" ]]; then urgency=2
    fi
  fi

  score=$(( (cat_weight * pri_weight) + urgency ))
  streak_display=""
  if [[ "$streak" -gt 0 ]]; then streak_display=" 🔥${streak}"; fi
  output+="$score|[$category] $title (${priority})${streak_display}|${due_date:-no due date}\n"
done < <(echo "$SCORED" | jq -c '.[]')

# --- Sort and display ---
echo "=== TOP 3 FOR: $USER_NAME ==="
echo ""
top3=$(printf "$output" | sort -t'|' -k1 -rn | head -3)
rank=1
while IFS='|' read -r score task due; do
  echo "$rank. $task — due: $due (score: $score)"
  (( rank++ ))
done <<< "$top3"

echo ""
echo "=== FULL RANKED LIST ==="
echo ""
rank=1
while IFS='|' read -r score task due; do
  echo "$rank. $task — due: $due (score: $score)"
  (( rank++ ))
done < <(printf "$output" | sort -t'|' -k1 -rn)
