#!/usr/bin/env bash
# LogCore OS — In-place update with automatic rollback
#
# Usage:
#   bash docker/update.sh              # one-shot update (pull + build + restart + health check)
#   bash docker/update.sh --watch      # daemon: apply update when flag file appears (every 60 s)
#   bash docker/update.sh --check      # print installed version and exit
#
# Auto-updates work by pairing this script with the in-app Admin → Updates panel:
#   1. Admin clicks "Apply Update" in the app.
#   2. App writes  brain/_system/pending_update.
#   3. This script (--watch mode) sees the flag and runs the update.
#   4. On success: writes new version to brain/_system/installed_version.json.
#   5. On failure: git resets to the previous commit, rebuilds, restarts (rollback).
#
# Start the watcher automatically by launching with:
#   bash launch.sh --auto-update

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$SCRIPT_DIR"
BRAIN_SYS="$REPO_ROOT/brain/_system"
FLAG_FILE="$BRAIN_SYS/pending_update"
RUNNING_FLAG="$BRAIN_SYS/update_running"
STATUS_FILE="$BRAIN_SYS/update_status.json"
HEARTBEAT_FILE="$BRAIN_SYS/update_heartbeat.json"
LOG_FILE="$BRAIN_SYS/update.log"
HEALTH_URL="http://localhost:8000/api/v1/health"
HEALTH_TIMEOUT=120
WATCH_INTERVAL=60

mkdir -p "$BRAIN_SYS"

# Load operator config (UPDATE_REQUIRE_SIGNATURE, …) from docker/.env if present.
if [[ -f "$DOCKER_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1090,SC1091
    source "$DOCKER_DIR/.env" 2>/dev/null || true
    set +a
fi

# ── Logging ───────────────────────────────────────────────────────────────────

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

# ── Status file ───────────────────────────────────────────────────────────────

write_status() {
    local result="$1" version="${2:-}"
    python3 -c "
import json, time
print(json.dumps({'result': '$result', 'timestamp': time.time(), 'version': '$version'}))
" > "$STATUS_FILE" 2>/dev/null || true
}

write_heartbeat() {
    python3 -c "import json, time; print(json.dumps({'last_seen': time.time()}))" \
        > "$HEARTBEAT_FILE" 2>/dev/null || true
}

write_installed_version() {
    local version="$1"
    python3 -c "import json; print(json.dumps({'version': '$version'}))" \
        > "$BRAIN_SYS/installed_version.json" 2>/dev/null || true
}

# ── Health check ──────────────────────────────────────────────────────────────

wait_healthy() {
    local elapsed=0
    while [[ $elapsed -lt $HEALTH_TIMEOUT ]]; do
        if curl -sf --max-time 3 "$HEALTH_URL" > /dev/null 2>&1; then
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done
    return 1
}

# ── Docker Compose helper ─────────────────────────────────────────────────────

compose_up() {
    docker compose \
        -f "$DOCKER_DIR/docker-compose.yml" \
        --project-directory "$DOCKER_DIR" \
        up --build -d >> "$LOG_FILE" 2>&1
}

# ── Rollback ──────────────────────────────────────────────────────────────────

do_rollback() {
    local prev_commit="$1"
    log "Rolling back to commit $prev_commit..."

    git -C "$REPO_ROOT" reset --hard "$prev_commit" >> "$LOG_FILE" 2>&1

    # Rebuild frontend from previous source (best-effort; use existing dist if it fails)
    npm --prefix "$REPO_ROOT/app/frontend" run build >> "$LOG_FILE" 2>&1 \
        || log "Frontend rebuild failed during rollback — using existing dist."

    compose_up

    if wait_healthy; then
        log "Rollback successful."
        write_status "rollback" "$prev_commit"
    else
        log "WARNING: App not healthy after rollback. Check logs:"
        log "  docker compose -f docker/docker-compose.yml logs app"
        write_status "rollback-unhealthy" "$prev_commit"
    fi
}

# ── Supply-chain: verify the incoming commit is signed ─────────────────────────
# Opt-in. When UPDATE_REQUIRE_SIGNATURE=true, the commit fetched from origin must
# carry a valid GPG signature — on the commit itself, or on an annotated tag that
# points at it — from a key trusted in the updater's GPG keyring. If it doesn't,
# the update is refused BEFORE anything is merged or built. This defends the
# auto-updater against a compromised origin or a MITM injecting malicious code.
#
# Default OFF so existing deployments (whose commits may be unsigned) keep
# updating. To turn it on:
#   1. GPG-sign your release commits or tags (git commit -S / git tag -s).
#   2. Import the release signing PUBLIC key into the keyring the updater runs
#      under (gpg --import release-pubkey.asc) and mark it trusted.
#   3. Set UPDATE_REQUIRE_SIGNATURE=true in docker/.env.

require_signature() {
    case "${UPDATE_REQUIRE_SIGNATURE:-false}" in
        true | 1 | yes | on) return 0 ;;
        *) return 1 ;;
    esac
}

verify_signature() {
    local commit="$1"
    require_signature || return 0   # verification disabled → allow

    log "UPDATE_REQUIRE_SIGNATURE=true — verifying GPG signature of $commit..."
    if ! command -v gpg &>/dev/null; then
        log "  gpg not installed — cannot verify signature; refusing update."
        return 1
    fi
    if git -C "$REPO_ROOT" verify-commit "$commit" >> "$LOG_FILE" 2>&1; then
        log "  Commit signature valid."
        return 0
    fi
    # Fall back to an annotated tag that points at this commit
    local tag
    tag="$(git -C "$REPO_ROOT" tag --points-at "$commit" 2>/dev/null | head -1)"
    if [[ -n "$tag" ]] && git -C "$REPO_ROOT" verify-tag "$tag" >> "$LOG_FILE" 2>&1; then
        log "  Tag signature valid ($tag)."
        return 0
    fi
    log "  No valid trusted GPG signature on $commit (or a tag pointing at it) — refusing update."
    return 1
}

# ── Core update ───────────────────────────────────────────────────────────────

do_update() {
    # Prevent concurrent updates
    if [[ -f "$RUNNING_FLAG" ]]; then
        log "Update already in progress — skipping."
        return 0
    fi
    touch "$RUNNING_FLAG"
    # Always clean up the running flag on exit
    trap 'rm -f "$RUNNING_FLAG"' EXIT

    log "=== LogCore OS update starting ==="

    # 1. Backup Brain before touching anything
    if [[ -f "$DOCKER_DIR/backup.sh" ]]; then
        log "Creating Brain backup..."
        bash "$DOCKER_DIR/backup.sh" >> "$LOG_FILE" 2>&1 \
            && log "Backup complete." \
            || log "Backup warning — continuing anyway."
    fi

    # 2. Save current state for rollback
    local prev_commit
    prev_commit="$(git -C "$REPO_ROOT" rev-parse HEAD)"
    log "Current commit: $prev_commit"

    # 3. Fetch latest code — but do NOT merge it into the working tree until it
    #    has passed signature verification, so unverified code never lands.
    log "Fetching latest code from origin/master..."
    git -C "$REPO_ROOT" fetch origin master >> "$LOG_FILE" 2>&1

    local new_commit
    new_commit="$(git -C "$REPO_ROOT" rev-parse FETCH_HEAD)"

    if [[ "$prev_commit" == "$new_commit" ]]; then
        log "Already up to date — nothing to do."
        rm -f "$RUNNING_FLAG"
        write_status "up-to-date"
        return 0
    fi

    # 3a. Verify the incoming commit's signature (no-op unless UPDATE_REQUIRE_SIGNATURE=true)
    if ! verify_signature "$new_commit"; then
        log "Signature verification failed — aborting update, working tree untouched."
        write_status "signature-failed" "$new_commit"
        rm -f "$RUNNING_FLAG"
        return 1
    fi

    # 3b. Land the verified commit (fast-forward only — refuse divergent history)
    if ! git -C "$REPO_ROOT" merge --ff-only "$new_commit" >> "$LOG_FILE" 2>&1; then
        log "Cannot fast-forward to $new_commit (divergent local history) — aborting."
        write_status "ff-failed" "$new_commit"
        rm -f "$RUNNING_FLAG"
        return 1
    fi
    log "New commit: $new_commit"

    # 4. Read new version
    local new_version="unknown"
    [[ -f "$REPO_ROOT/VERSION" ]] && new_version="$(tr -d '[:space:]' < "$REPO_ROOT/VERSION")"

    # 5. Build frontend
    log "Installing frontend dependencies..."
    if ! npm --prefix "$REPO_ROOT/app/frontend" ci --silent >> "$LOG_FILE" 2>&1; then
        log "npm ci failed — rolling back..."
        do_rollback "$prev_commit"
        rm -f "$RUNNING_FLAG"
        return 1
    fi

    log "Building frontend..."
    if ! npm --prefix "$REPO_ROOT/app/frontend" run build >> "$LOG_FILE" 2>&1; then
        log "Frontend build failed — rolling back..."
        do_rollback "$prev_commit"
        rm -f "$RUNNING_FLAG"
        return 1
    fi
    log "Frontend built."

    # 6. Rebuild Docker image and restart containers
    log "Rebuilding Docker image and restarting containers..."
    if ! compose_up; then
        log "Docker rebuild failed — rolling back..."
        do_rollback "$prev_commit"
        rm -f "$RUNNING_FLAG"
        return 1
    fi

    # 7. Health check
    log "Waiting for health check (up to ${HEALTH_TIMEOUT}s)..."
    if wait_healthy; then
        write_installed_version "$new_version"
        write_status "success" "$new_version"
        log "=== Update successful! Now running v${new_version} ==="
        rm -f "$RUNNING_FLAG"
        return 0
    else
        log "Health check failed after rebuild — rolling back..."
        do_rollback "$prev_commit"
        rm -f "$RUNNING_FLAG"
        return 1
    fi
}

# ── Watch mode (daemon) ───────────────────────────────────────────────────────

watch_mode() {
    log "Update watcher started (PID $$, polling every ${WATCH_INTERVAL}s)."
    log "Watching: $FLAG_FILE"
    while true; do
        write_heartbeat
        if [[ -f "$FLAG_FILE" ]]; then
            log "Pending update flag detected — applying update."
            rm -f "$FLAG_FILE"
            do_update || log "Update failed — see log above."
        fi
        sleep "$WATCH_INTERVAL"
    done
}

# ── Main ──────────────────────────────────────────────────────────────────────

case "${1:-}" in
    --watch)
        watch_mode
        ;;
    --cron)
        # Designed for cron (runs every minute). Writes heartbeat, applies update if flag present, then exits.
        write_heartbeat
        if [[ -f "$FLAG_FILE" ]]; then
            rm -f "$FLAG_FILE"
            do_update || true
        fi
        ;;
    --check)
        installed=""
        ver_file="$BRAIN_SYS/installed_version.json"
        if [[ -f "$ver_file" ]] && command -v python3 &>/dev/null; then
            installed="$(python3 -c "import json; d=json.load(open('$ver_file')); print(d.get('version',''))" 2>/dev/null || true)"
        fi
        [[ -f "$REPO_ROOT/VERSION" ]] && repo_ver="$(tr -d '[:space:]' < "$REPO_ROOT/VERSION")" || repo_ver="unknown"
        echo "Installed : ${installed:-unknown}"
        echo "Repo HEAD : $repo_ver ($(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'no git'))"
        ;;
    *)
        do_update
        ;;
esac
