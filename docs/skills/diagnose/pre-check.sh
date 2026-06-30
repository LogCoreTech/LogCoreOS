#!/usr/bin/env bash
# diagnose skill — automated pre-checks (things a script can verify faster than an AI)
# Run this first; hand the output to the AI along with diagnose.md for the full audit.

set -uo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
BACKEND="$REPO_ROOT/app/backend"
FRONTEND="$REPO_ROOT/app/frontend/src"

pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; ISSUES=$((ISSUES + 1)); }

ISSUES=0

echo "======================================"
echo "  LogCoreOS — Automated Pre-Checks"
echo "======================================"
echo ""

# ── 1. Module registry sync ────────────────────────────────────────────────────
echo "── Module registry sync"

fe_ids=$(grep -oP "id: '\K[^']+" "$FRONTEND/lib/constants.js" | sort)
be_ids=$(grep -oP "\"[a-z]+\"" "$BACKEND/routers/auth.py" | grep -A50 "VALID_MODULE_IDS" | head -20 | grep -oP '"[a-z]+"' | tr -d '"' | sort)

if [ "$fe_ids" = "$be_ids" ]; then
  pass "ALL_MODULES (frontend) matches VALID_MODULE_IDS (backend)"
else
  fail "Module ID mismatch"
  echo "  Frontend: $fe_ids"
  echo "  Backend:  $be_ids"
fi
echo ""

# ── 2. Services don't import from routers ─────────────────────────────────────
echo "── Services must not import from routers"

violations=$(grep -rl "from routers\|import routers" "$BACKEND/services/" 2>/dev/null || true)
if [ -z "$violations" ]; then
  pass "No service imports routers"
else
  fail "Service imports routers — layering violation"
  echo "$violations" | sed 's/^/  /'
fi
echo ""

# ── 3. Atomic writes — no bare open/write_text on brain paths ─────────────────
echo "── Atomic write rule (no bare open/write_text in routers or services)"

raw_writes=$(grep -rn "\.write_text\|open(.*['\"]w['\"]" "$BACKEND/routers/" "$BACKEND/services/" 2>/dev/null || true)
if [ -z "$raw_writes" ]; then
  pass "All writes go through write_json / write_markdown"
else
  fail "Bare file writes found — use write_json() or write_markdown() instead"
  echo "$raw_writes" | sed 's/^/  /'
fi
echo ""

# ── 4. Rate limiting — endpoints with no Depends(_*limit*) ────────────────────
echo "── Rate limiting coverage"

unrated=$(grep -rn "@router\." "$BACKEND/routers/" | grep -v "test_" \
  | awk -F: '{print $1":"$2}' \
  | while IFS=: read file line; do
      # check if the function after this decorator has a rate limit dependency
      block=$(sed -n "${line},$((line+10))p" "$file")
      if ! echo "$block" | grep -q "_limit\|rate_limit"; then
        echo "  $file:$line — $(echo "$block" | head -1)"
      fi
    done)

if [ -z "$unrated" ]; then
  pass "All checked endpoints have rate limiting"
else
  echo "[INFO] Endpoints without rate limiting (verify each is intentional):"
  echo "$unrated"
fi
echo ""

# ── 5. ModuleRoute guard in App.jsx ───────────────────────────────────────────
echo "── Frontend ModuleRoute guard"

module_routes=$(grep -c "ModuleRoute" "$FRONTEND/App.jsx" 2>/dev/null || echo 0)
if [ "$module_routes" -gt 0 ]; then
  pass "ModuleRoute found in App.jsx ($module_routes occurrences)"
else
  fail "No ModuleRoute in App.jsx — disabled modules won't block direct URL access"
fi
echo ""

# ── 6. api.js credentials:include ─────────────────────────────────────────────
echo "── Frontend fetch calls use credentials:include"

bare_fetch=$(grep -n "fetch(" "$FRONTEND/lib/api.js" | grep -v "credentials" || true)
if [ -z "$bare_fetch" ]; then
  pass "All fetch() calls include credentials"
else
  fail "fetch() without credentials:include found in api.js"
  echo "$bare_fetch" | sed 's/^/  /'
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "======================================"
if [ "$ISSUES" -eq 0 ]; then
  echo "Pre-checks: CLEAN ($ISSUES issues)"
else
  echo "Pre-checks: $ISSUES ISSUE(S) FOUND — review above before running full audit"
fi
echo "======================================"
echo ""
echo "Next: hand this output to an AI with diagnose.md for the full audit."
