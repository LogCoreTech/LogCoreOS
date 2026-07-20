#!/usr/bin/env bash
# LogCore OS — In-place update with automatic rollback
#
# Usage:
#   bash docker/update.sh              # one-shot update (pull + build + restart + health check)
#   bash docker/update.sh --watch      # daemon: apply update when flag file appears (every 60 s)
#   bash docker/update.sh --check      # print installed version and exit
#
# Updates are ATOMIC: the script installs exactly the commit the latest
# published GitHub release tag points at — commits pushed to master after a
# release do not ship until the next release. Set UPDATE_CHANNEL=edge in
# docker/.env to track origin/master instead (dev boxes).
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
    printf '{"result": "%s", "timestamp": %s, "version": "%s"}\n' \
        "$result" "$(date +%s)" "$version" > "$STATUS_FILE" 2>/dev/null || true
}

write_heartbeat() {
    printf '{"last_seen": %s}\n' "$(date +%s)" > "$HEARTBEAT_FILE" 2>/dev/null || true
}

# The ONLY runtime source of the app's "current version" (Admin → Updates reads
# installed_version.json via the backend). If this write fails, the app keeps
# reporting the old version forever even though the new code is running — so
# verify the write landed and complain loudly if it didn't.
write_installed_version() {
    local version="$1" file="$BRAIN_SYS/installed_version.json"
    printf '{"version": "%s"}\n' "$version" > "$file" 2>> "$LOG_FILE" || true
    if ! grep -q "\"${version}\"" "$file" 2>/dev/null; then
        log "ERROR: failed to record installed version ${version} in ${file}."
        log "  The app will keep showing the previous version until this file is writable"
        log "  (check ownership/permissions of $BRAIN_SYS)."
        return 1
    fi
    return 0
}

# SSH remotes (git@github.com:…) need a key the cron user can read — a cron
# installed under a different user (e.g. root after a sudo launch.sh) can't
# fetch and the instance is stranded until someone SSHes in. The repo is public,
# so the same repo is always fetchable over HTTPS with no credentials: derive
# that URL from origin so forks keep tracking their own fork.
https_equivalent_of_origin() {
    local url
    # Raw configured value (not `remote get-url`, which applies insteadOf rewrites)
    url="$(git -C "$REPO_ROOT" config --get remote.origin.url 2>/dev/null)" || return 1
    case "$url" in
        git@github.com:*)       printf 'https://github.com/%s\n' "${url#git@github.com:}" ;;
        ssh://git@github.com/*) printf 'https://github.com/%s\n' "${url#ssh://git@github.com/}" ;;
        *) return 1 ;;
    esac
}

# The GitHub "owner/repo" path of the origin remote (fork-preserving), or fail.
github_repo_path() {
    local url path
    url="$(git -C "$REPO_ROOT" config --get remote.origin.url 2>/dev/null)" || return 1
    case "$url" in
        git@github.com:*)        path="${url#git@github.com:}" ;;
        ssh://git@github.com/*)  path="${url#ssh://git@github.com/}" ;;
        https://github.com/*)    path="${url#https://github.com/}" ;;
        http://github.com/*)     path="${url#http://github.com/}" ;;
        *) return 1 ;;
    esac
    printf '%s\n' "${path%.git}"
}

# Tag name of the latest published GitHub release for the origin repo.
# This is what makes updates ATOMIC: instances install exactly the commit the
# release tag points at — commits pushed to master after a release do NOT ship
# until the next release is published.
latest_release_tag() {
    local repo_path
    repo_path="$(github_repo_path)" || return 1
    curl -sf --max-time 15 "https://api.github.com/repos/${repo_path}/releases/latest" \
        2>> "$LOG_FILE" \
        | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1
}

# A previous update can deploy new code but die (or fail the write above) before
# the version is recorded; every later run then no-ops on "already up to date"
# and the stale version sticks forever. Heal that here: if the working tree's
# VERSION differs from the recorded one and the app is up, re-stamp.
restamp_if_stale() {
    local repo_version="" stamped=""
    [[ -f "$REPO_ROOT/VERSION" ]] && repo_version="$(tr -d '[:space:]' < "$REPO_ROOT/VERSION")"
    [[ -z "$repo_version" ]] && return 0
    stamped="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
        "$BRAIN_SYS/installed_version.json" 2>/dev/null | head -1)"
    [[ "$repo_version" == "$stamped" ]] && return 0
    if curl -sf --max-time 3 "$HEALTH_URL" > /dev/null 2>&1; then
        log "Recorded version (${stamped:-none}) lags the deployed tree (${repo_version}) — re-stamping."
        write_installed_version "$repo_version" || true
    fi
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

    # 3. Decide what to install. Default: the latest published RELEASE tag —
    #    updates are atomic, instances only ever run tagged release states, and
    #    commits pushed to master after a release do NOT ship until the next
    #    release. Set UPDATE_CHANNEL=edge in docker/.env to track origin/master
    #    instead (dev boxes).
    local channel="${UPDATE_CHANNEL:-release}"
    local latest_tag="" fetch_spec="" resolve_ref="" target_desc=""
    if [[ "$channel" == "edge" ]]; then
        fetch_spec="master"
        resolve_ref="FETCH_HEAD"
        target_desc="origin/master (UPDATE_CHANNEL=edge)"
    else
        latest_tag="$(latest_release_tag || true)"
        if [[ -z "$latest_tag" ]]; then
            log "Could not determine the latest release tag (GitHub API unreachable, no release published, or non-GitHub remote) — aborting."
            log "  Set UPDATE_CHANNEL=edge in docker/.env to track origin/master instead."
            write_status "tag-failed"
            rm -f "$RUNNING_FLAG"
            return 1
        fi
        fetch_spec="refs/tags/${latest_tag}:refs/tags/${latest_tag}"
        resolve_ref="refs/tags/${latest_tag}"
        target_desc="release ${latest_tag}"
    fi

    #    Fetch the target — but do NOT merge it into the working tree until it
    #    has passed signature verification, so unverified code never lands.
    #    A failed fetch MUST abort here: this function is invoked as
    #    `do_update || …`, which disables errexit inside it, and continuing on a
    #    stale FETCH_HEAD once rebuilt the old tree and stamped it "successful".
    log "Fetching ${target_desc}..."
    if ! git -C "$REPO_ROOT" fetch --force origin "$fetch_spec" >> "$LOG_FILE" 2>&1; then
        local https_url=""
        https_url="$(https_equivalent_of_origin || true)"
        if [[ -n "$https_url" ]] \
            && git -C "$REPO_ROOT" fetch --force "$https_url" "$fetch_spec" >> "$LOG_FILE" 2>&1; then
            log "origin fetch failed (SSH credentials?) — fell back to $https_url and continued."
            log "  Fix the remote permanently with: git remote set-url origin $https_url"
        else
            log "git fetch failed — cannot reach origin. Check the remote URL and credentials (see log above)."
            log "  Note: an SSH remote (git@github.com:…) needs a key the updater's cron user can read;"
            log "  the public HTTPS remote needs none: git remote set-url origin https://github.com/LogCoreTech/LogCoreOS.git"
            write_status "fetch-failed"
            rm -f "$RUNNING_FLAG"
            return 1
        fi
    fi

    local new_commit
    if ! new_commit="$(git -C "$REPO_ROOT" rev-parse --verify "${resolve_ref}^{commit}" 2>> "$LOG_FILE")" \
        || [[ -z "$new_commit" ]]; then
        log "Could not resolve the fetched commit — aborting, working tree untouched."
        write_status "fetch-failed"
        rm -f "$RUNNING_FLAG"
        return 1
    fi

    # Up to date when the target commit is already contained in the current
    # checkout (covers equality, and an edge-channel checkout that's AHEAD of
    # the latest release — never "update" backwards onto an older tag).
    if git -C "$REPO_ROOT" merge-base --is-ancestor "$new_commit" "$prev_commit" 2>> "$LOG_FILE"; then
        log "Already up to date (${target_desc} is contained in the current checkout) — nothing to do."
        restamp_if_stale
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
        if write_installed_version "$new_version"; then
            write_status "success" "$new_version"
        else
            # Code deployed fine but the version record didn't land — surface it
            # instead of pretending everything's consistent.
            write_status "success-stamp-failed" "$new_version"
        fi
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
