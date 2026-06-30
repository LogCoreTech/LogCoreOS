#!/usr/bin/env bash
# run-tests skill — executes the LogCoreOS backend test suite and prints a structured report

set -uo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
BACKEND="$REPO_ROOT/app/backend"

if [ ! -d "$BACKEND" ]; then
  echo "ERROR: backend directory not found at $BACKEND"
  exit 1
fi

echo "=============================="
echo "  LogCoreOS — Backend Tests"
echo "=============================="
echo ""

cd "$BACKEND"

# Run pytest; capture output and exit code separately
output=$(pytest tests/ -v --tb=short 2>&1) || true
exit_code=$?

echo "$output"
echo ""
echo "------------------------------"

# Parse counts from the summary line  (e.g. "5 passed, 1 failed, 2 errors in 3.21s")
passed=$(echo "$output" | grep -oP '\d+(?= passed)'  || echo 0)
failed=$(echo "$output" | grep -oP '\d+(?= failed)'  || echo 0)
errors=$(echo "$output" | grep -oP '\d+(?= error)'   || echo 0)
total=$(( ${passed:-0} + ${failed:-0} + ${errors:-0} ))

if [ "${failed:-0}" -gt 0 ] || [ "${errors:-0}" -gt 0 ]; then
  status="RED"
else
  status="GREEN"
fi

echo ""
echo "TEST RESULTS"
echo "------------"
echo "Total:   $total"
echo "Passed:  ${passed:-0}"
echo "Failed:  ${failed:-0}"
echo "Errors:  ${errors:-0}"
echo "Status:  $status"

if [ "$status" = "RED" ]; then
  echo ""
  echo "Failing tests:"
  echo "$output" | grep -E "^FAILED|^ERROR" | sed 's/^/  - /'
  exit 1
fi
