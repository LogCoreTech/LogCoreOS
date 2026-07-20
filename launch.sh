#!/usr/bin/env bash
# LogCore OS — Launch Script
# Builds the frontend, configures the environment, and starts the Docker stack.
#
# Usage:
#   bash launch.sh                  # first-time setup or normal restart
#   bash launch.sh --install-deps   # auto-install prerequisites (Linux only), then launch
#   bash launch.sh --reconfigure    # re-run setup even if docker/.env already exists
#   bash launch.sh --skip-build     # skip npm build (requires app/frontend/dist/ to exist)
#   bash launch.sh --tunnel-token <token>   # set/replace the Cloudflare Tunnel token
#                                           # (also accepted as --tunnel-token=<token>)
#
# Updates are managed from Admin → Updates in the app. launch.sh installs the update
# cron daemon automatically on every run. Toggle auto-update on/off from the Admin panel.
#
# Requirements: Docker (with Compose plugin v2), Node.js 20+, curl
# On Linux, pass --install-deps to have the script install these automatically.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
DOCKER_DIR="$REPO_ROOT/docker"
ENV_FILE="$DOCKER_DIR/.env"
ENV_EXAMPLE="$DOCKER_DIR/.env.example"
FRONTEND_DIR="$REPO_ROOT/app/frontend"
DIST_DIR="$FRONTEND_DIR/dist"
BRAIN_HOSTING="$REPO_ROOT/brain/hosting.json"
HEALTH_URL="http://localhost:8000/api/v1/health"
HEALTH_TIMEOUT=90
HEALTH_INTERVAL=3

FLAG_RECONFIGURE=false
FLAG_SKIP_BUILD=false
FLAG_INSTALL_DEPS=false
FLAG_TUNNEL_TOKEN=""

# ── Flags ─────────────────────────────────────────────────────────────────────

parse_flags() {
  local expect_token=false
  for arg in "$@"; do
    if [[ "$expect_token" == "true" ]]; then
      FLAG_TUNNEL_TOKEN="$arg"
      expect_token=false
      continue
    fi
    case "$arg" in
      --reconfigure)     FLAG_RECONFIGURE=true    ;;
      --skip-build)      FLAG_SKIP_BUILD=true     ;;
      --install-deps)    FLAG_INSTALL_DEPS=true   ;;
      --tunnel-token)    expect_token=true        ;;
      --tunnel-token=*)  FLAG_TUNNEL_TOKEN="${arg#*=}" ;;
      *)
        echo "ERROR: Unknown flag: $arg"
        echo "Usage: bash launch.sh [--install-deps] [--reconfigure] [--skip-build] [--tunnel-token <token>]"
        exit 1
        ;;
    esac
  done
  if [[ "$expect_token" == "true" ]]; then
    echo "ERROR: --tunnel-token requires a value."
    exit 1
  fi
}

# ── Logging ───────────────────────────────────────────────────────────────────

log_step() { echo "==> $1"; }
log_info()  { echo "    $1"; }
log_warn()  { echo "    WARNING: $1"; }
die()       { echo "    ERROR: $1"; exit 1; }

# ── Docker group ──────────────────────────────────────────────────────────────

ensure_docker_group() {
  # Fast path: Docker socket is already accessible.
  if docker info &>/dev/null 2>&1; then
    return 0
  fi

  local user
  user="$(id -un)"

  # User is listed in the docker group in /etc/group but the current session
  # was opened before they were added — re-exec via 'sg docker' to activate
  # the group without requiring a full logout/login.
  if getent group docker 2>/dev/null | grep -qw "$user" && ! id -Gn | grep -qw docker; then
    log_info "Docker group membership isn't active in this session."
    local args
    args="$(printf '%q ' "$@")"
    if command -v sg &>/dev/null; then
      log_info "Re-launching via 'sg docker' (no logout needed)..."
      exec sg docker -c "bash \"$SCRIPT_DIR/launch.sh\" $args"
    elif [[ -z "${SUDO_USER:-}" ]] && command -v sudo &>/dev/null; then
      # Re-exec through sudo so PAM re-initialises supplementary groups (picks
      # up the docker group that was just added). SUDO_USER being set on the
      # re-launched process means PAM ran; if docker is still inactive we stop
      # rather than loop.
      log_info "Re-launching via sudo to activate docker group (no logout needed)..."
      exec sudo -E -u "$user" bash "$SCRIPT_DIR/launch.sh" "$@"
    else
      die "Docker group membership is not active and neither 'sg' nor 'sudo' are available.
    Log out and back in (or open a new terminal), then re-run:
      bash \"$SCRIPT_DIR/launch.sh\" $args"
    fi
  fi

  # User isn't in the docker group at all.
  if ! getent group docker 2>/dev/null | grep -qw "$user"; then
    die "Cannot connect to Docker. '$user' is not in the docker group.
    Fix it with:
      sudo usermod -aG docker $user
    Then either log out and back in, or run:
      newgrp docker"
  fi
}

# ── Dependency installation ───────────────────────────────────────────────────

detect_os() {
  case "$(uname -s)" in
    Linux*)            echo "linux"   ;;
    Darwin*)           echo "macos"   ;;
    CYGWIN*|MINGW*|MSYS*) echo "windows" ;;
    *)                 echo "unknown" ;;
  esac
}

install_deps() {
  [[ "$FLAG_INSTALL_DEPS" == "true" ]] || return 0

  local os
  os="$(detect_os)"

  if [[ "$os" != "linux" ]]; then
    log_warn "Auto-install is only supported on Linux. Install prerequisites manually:"
    log_info "  Docker:  https://docs.docker.com/engine/install/"
    log_info "  Node.js: https://nodejs.org/en/download/"
    log_info "  curl:    use your system package manager"
    return 0
  fi

  log_step "Installing prerequisites"

  # SECURITY NOTE — trust-on-first-use bootstrap.
  # The Docker and Node.js installs below use the vendors' official
  # `curl … | sudo sh` bootstrap scripts (get.docker.com, deb/rpm.nodesource.com).
  # These run vendor-authored code as root, fetched over HTTPS, with no
  # independent checksum/signature verification — the standard but inherently
  # trust-on-first-use pattern. It only runs when you explicitly pass
  # --install-deps. If you'd rather not pipe a remote script to root, install
  # Docker Engine + Compose and Node.js 20+ yourself from the official docs and
  # run launch.sh WITHOUT --install-deps:
  #   Docker:  https://docs.docker.com/engine/install/
  #   Node.js: https://nodejs.org/en/download/
  log_warn "--install-deps runs the official Docker/Node bootstrap scripts as root"
  log_info "  (curl … | sudo sh over HTTPS, no checksum pinning — trust-on-first-use)."
  log_info "  To avoid this, install Docker + Node.js 20 manually and omit --install-deps."

  local pm
  if command -v apt-get &>/dev/null; then
    pm="apt"
  elif command -v dnf &>/dev/null; then
    pm="dnf"
  elif command -v yum &>/dev/null; then
    pm="yum"
  else
    die "No supported package manager found (apt, dnf, yum). Install prerequisites manually."
  fi

  # curl — needed for everything below
  if ! command -v curl &>/dev/null; then
    log_info "Installing curl..."
    case "$pm" in
      apt) sudo apt-get update -qq && sudo apt-get install -y curl ;;
      dnf) sudo dnf install -y curl ;;
      yum) sudo yum install -y curl ;;
    esac
  fi

  # Docker Engine + Compose plugin (official install script covers both)
  if ! command -v docker &>/dev/null; then
    log_info "Installing Docker..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$(id -un)"
    log_info "Added $(id -un) to the docker group."
  fi

  # Node.js 20+ via NodeSource
  local need_node=true
  if [[ "$FLAG_SKIP_BUILD" == "true" && -d "$DIST_DIR" ]]; then
    need_node=false
  fi

  if [[ "$need_node" == "true" ]] && ! command -v node &>/dev/null; then
    log_info "Installing Node.js 20..."
    case "$pm" in
      apt)
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt-get install -y nodejs
        ;;
      dnf|yum)
        curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
        sudo "$pm" install -y nodejs
        ;;
    esac
  fi

  log_info "Prerequisites ready."
}

# ── Prerequisites ─────────────────────────────────────────────────────────────

check_prerequisites() {
  log_step "Checking prerequisites"

  if ! command -v docker &>/dev/null; then
    die "Docker is not installed.
    Install it from: https://docs.docker.com/engine/install/
    Then re-run this script."
  fi

  if ! docker info &>/dev/null 2>&1; then
    die "Docker is installed but the daemon isn't running.
    Start it:  sudo systemctl start docker
    Status:    sudo systemctl status docker"
  fi

  if ! docker compose version &>/dev/null 2>&1; then
    if command -v docker-compose &>/dev/null; then
      die "docker-compose v1 is installed but is not supported.
    Upgrade to the Docker Compose v2 plugin:
    https://docs.docker.com/compose/install/"
    fi
    die "Docker Compose plugin (v2) is not installed.
    Install it from: https://docs.docker.com/compose/install/"
  fi

  if ! command -v curl &>/dev/null; then
    die "curl is not installed (required for the health check).
    Install it: sudo apt-get install curl   # Debian/Ubuntu
                sudo dnf install curl       # Fedora/RHEL"
  fi

  local need_node=true
  if [[ "$FLAG_SKIP_BUILD" == "true" && -d "$DIST_DIR" ]]; then
    need_node=false
  fi

  if [[ "$need_node" == "true" ]]; then
    if ! command -v node &>/dev/null || ! command -v npm &>/dev/null; then
      die "Node.js is not installed (required to build the frontend).
    Install Node.js 20+ from: https://nodejs.org/en/download/
    Or via nvm:               https://github.com/nvm-sh/nvm

    If app/frontend/dist/ already exists you can skip the build:
      bash launch.sh --skip-build"
    fi
  fi

  log_info "All prerequisites found."
}

# ── Secret key ────────────────────────────────────────────────────────────────

generate_secret_key() {
  if command -v python3 &>/dev/null; then
    python3 -c "import secrets; print(secrets.token_hex(32))"
  elif command -v openssl &>/dev/null; then
    openssl rand -hex 32
  else
    tr -dc 'a-f0-9' < /dev/urandom | head -c 64
  fi
}

# ── .env helpers ──────────────────────────────────────────────────────────────

env_set() {
  local key="$1" value="$2"
  if grep -qE "^#?${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^#\?${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

env_get() {
  grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2-
}

# ── Environment setup ─────────────────────────────────────────────────────────

generate_env() {
  log_step "Creating docker/.env"

  cp "$ENV_EXAMPLE" "$ENV_FILE"

  local secret_key
  secret_key="$(generate_secret_key)"
  env_set SECRET_KEY          "$secret_key"
  # Secure by default. The UI is same-origin with the API, so no CORS is needed;
  # leave ALLOWED_ORIGINS empty (deny cross-origin) and keep the auth cookie Secure.
  # For plain-HTTP LAN dev, flip COOKIE_SECURE=false and set ALLOWED_ORIGINS here,
  # or use Admin → Hosting after first login.
  env_set ALLOWED_ORIGINS     ""
  env_set COOKIE_SECURE       "true"
  env_set TRUST_PROXY_HEADERS "false"
  env_set DOCKER_GID          "$(stat -c '%g' /var/run/docker.sock 2>/dev/null || echo '999')"

  # Strong per-install n8n keys (fresh install → no existing n8n data, so it is
  # safe to set the encryption key now). Never regenerated for an existing .env.
  env_set N8N_API_KEY         "$(generate_secret_key)"
  env_set N8N_ENCRYPTION_KEY  "$(generate_secret_key)"

  log_info "docker/.env created with a generated SECRET_KEY."
  log_info "After first login, go to Admin → AI Settings to add your API key."
  log_info "Go to Admin → Hosting to enable HTTPS/tunnel mode."
}

# ── Tunnel token sync ─────────────────────────────────────────────────────────

sync_tunnel_token() {
  [[ -f "$BRAIN_HOSTING" ]] || return 0
  command -v python3 &>/dev/null || return 0

  local proxy_type token
  proxy_type="$(python3 -c "import json; d=json.load(open('$BRAIN_HOSTING')); print(d.get('proxy_type',''))" 2>/dev/null || true)"
  token="$(python3 -c "import json; d=json.load(open('$BRAIN_HOSTING')); print(d.get('tunnel_token',''))" 2>/dev/null || true)"

  if [[ "$proxy_type" == "cloudflare" && -n "$token" ]]; then
    env_set CLOUDFLARE_TUNNEL_TOKEN "$token"
    log_info "Cloudflare tunnel token synced from brain/hosting.json."
  fi
}

# ── Brain ownership ───────────────────────────────────────────────────────────

fix_brain_ownership() {
  # The app container runs as appuser (uid 1000). When the repo is cloned by
  # root — the default on a fresh VPS — brain/ is root-owned and the app
  # crash-loops at startup with PermissionError on /data/brain.
  local app_uid=1000 app_gid=1000 owner
  owner="$(stat -c '%u' "$REPO_ROOT/brain" 2>/dev/null || echo "")"
  [[ -n "$owner" && "$owner" != "$app_uid" ]] || return 0

  if [[ "$(id -u)" -eq 0 ]]; then
    chown -R "$app_uid:$app_gid" "$REPO_ROOT/brain"
    log_info "brain/ ownership set to uid $app_uid (app container user)."
  else
    log_warn "brain/ is owned by uid $owner but the app container runs as uid $app_uid."
    log_warn "If the app fails to start with a brain/ PermissionError, run:"
    log_warn "  sudo chown -R $app_uid:$app_gid \"$REPO_ROOT/brain\""
  fi
}

# ── Frontend build ────────────────────────────────────────────────────────────

build_frontend() {
  if [[ "$FLAG_SKIP_BUILD" == "true" ]]; then
    if [[ -d "$DIST_DIR" ]]; then
      log_info "Skipping frontend build (--skip-build, dist/ exists)."
      return 0
    else
      die "--skip-build was passed but $DIST_DIR does not exist. Remove the flag and re-run."
    fi
  fi

  log_step "Building frontend"
  npm --prefix "$FRONTEND_DIR" ci
  npm --prefix "$FRONTEND_DIR" run build

  [[ -d "$DIST_DIR" ]] || die "Build finished but $DIST_DIR was not created. Check the Vite config."
  log_info "Frontend built: $DIST_DIR"
}

# ── Docker ────────────────────────────────────────────────────────────────────

ensure_n8n_env() {
  local n8n_env="$DOCKER_DIR/n8n.env"
  if [[ ! -f "$n8n_env" ]]; then
    touch "$n8n_env"
    log_info "Created empty docker/n8n.env (populated by LogCore when Infisical is connected)."
  fi
}

wait_for_ntfy() {
  local elapsed=0
  while [[ $elapsed -lt 30 ]]; do
    curl -sf --max-time 2 "http://127.0.0.1:5680/v1/health" > /dev/null 2>&1 && return 0
    sleep 2
    elapsed=$((elapsed + 2))
  done
  return 1
}

# ntfy ships with no auth by default — any client can publish OR subscribe to
# any topic. That's an acceptable trust model for a LAN-only instance (the
# random channel ID is the only lock, same as the notification-channel design
# documented in Help → Notifications), but it stops being acceptable the moment
# ntfy gets a public hostname (e.g. mapped through the Cloudflare tunnel — see
# the ports note on the ntfy service in docker-compose.yml): an unauthenticated
# publish endpoint on the open internet lets anyone spoof push notifications to
# a leaked or guessed channel. This provisions ONE admin "publisher" account for
# the app itself to authenticate with, then flips ntfy's default access to
# read-only — anonymous subscribe keeps working with zero setup for every family
# member, but publishing now requires this account's token.
#
# Idempotent: skipped once NTFY_PUBLISH_TOKEN is already recorded in docker/.env
# (never silently rotates/reprovisions on a normal relaunch). Fails OPEN: if any
# step here breaks — e.g. a future ntfy release changes its CLI — this logs a
# warning and leaves the server in its default read-write mode rather than
# risking a silent full notification outage. Re-running launch.sh retries it.
provision_ntfy_auth() {
  if [[ -n "$(env_get NTFY_PUBLISH_TOKEN)" ]]; then
    return 0
  fi
  log_step "Provisioning ntfy publisher account"

  if ! wait_for_ntfy; then
    log_warn "ntfy didn't come up in time — leaving it unauthenticated (open publish, ID-gated read)."
    log_warn "Re-run launch.sh to retry provisioning."
    return 0
  fi

  local pw token
  pw="$(generate_secret_key)"
  if ! printf '%s\n%s\n' "$pw" "$pw" | docker compose \
      -f "$DOCKER_DIR/docker-compose.yml" --project-directory "$DOCKER_DIR" \
      exec -T ntfy ntfy user add --role=admin logcore-publisher >/dev/null 2>&1; then
    log_warn "Could not create the ntfy publisher account — leaving ntfy unauthenticated."
    log_warn "Notifications still work (open publish); re-run launch.sh later to retry."
    return 0
  fi

  token="$(docker compose \
      -f "$DOCKER_DIR/docker-compose.yml" --project-directory "$DOCKER_DIR" \
      exec -T ntfy ntfy token add logcore-publisher 2>/dev/null | grep -oE 'tk_[A-Za-z0-9]+' | head -1)"
  if [[ -z "$token" ]]; then
    log_warn "ntfy publisher account created but no token could be extracted."
    log_warn "Check manually: docker compose exec ntfy ntfy token add logcore-publisher"
    return 0
  fi

  env_set NTFY_PUBLISH_TOKEN "$token"
  env_set NTFY_AUTH_DEFAULT_ACCESS "read-only"
  log_info "ntfy publisher account created — anonymous subscribe still works; publish now requires this token."
}

launch_containers() {
  log_step "Starting Docker containers"
  ensure_n8n_env
  if [[ -z "$(env_get NTFY_PUBLISH_TOKEN)" ]]; then
    # Bring ntfy up alone first so we can provision its auth before the app
    # container is created with the (currently empty) NTFY_PUBLISH_TOKEN.
    docker compose -f "$DOCKER_DIR/docker-compose.yml" --project-directory "$DOCKER_DIR" up -d ntfy
    provision_ntfy_auth
  fi
  docker compose \
    -f "$DOCKER_DIR/docker-compose.yml" \
    --project-directory "$DOCKER_DIR" \
    up --build -d
}

# ── Health check ──────────────────────────────────────────────────────────────

wait_for_health() {
  log_step "Waiting for app to become healthy"
  local elapsed=0 dots=0

  while [[ $elapsed -lt $HEALTH_TIMEOUT ]]; do
    if curl -sf --max-time 3 "$HEALTH_URL" > /dev/null 2>&1; then
      echo ""
      log_info "App is healthy (${elapsed}s)."
      return 0
    fi
    printf "."
    dots=$((dots + 1))
    if [[ $((dots % 20)) -eq 0 ]]; then printf " ${elapsed}s\n"; fi
    sleep "$HEALTH_INTERVAL"
    elapsed=$((elapsed + HEALTH_INTERVAL))
  done

  echo ""
  log_warn "App did not respond within ${HEALTH_TIMEOUT}s."
  log_warn "It may still be starting. Check with:"
  log_warn "  curl $HEALTH_URL"
  log_warn "  docker compose -f docker/docker-compose.yml logs app"
}

# ── Version stamp ─────────────────────────────────────────────────────────────

write_installed_version() {
  [[ -f "$REPO_ROOT/VERSION" ]] || return 0
  local version brain_sys
  version="$(tr -d '[:space:]' < "$REPO_ROOT/VERSION")"
  brain_sys="$REPO_ROOT/brain/_system"
  mkdir -p "$brain_sys"
  if command -v python3 &>/dev/null; then
    python3 -c "import json; print(json.dumps({'version': '$version'}))" \
      > "$brain_sys/installed_version.json"
    log_info "Installed version stamped: $version"
  fi
}

# ── Auto-update watcher ───────────────────────────────────────────────────────

install_update_cron() {
  if [[ ! -f "$DOCKER_DIR/update.sh" ]]; then
    log_warn "docker/update.sh not found — skipping update cron setup."
    return 0
  fi

  if ! command -v crontab &>/dev/null; then
    log_warn "crontab not available — update cron not installed. Run update.sh manually to apply updates."
    return 0
  fi

  # Idempotent: remove existing logcore-auto-update line, then re-add.
  local marker="# logcore-auto-update"
  local cron_line="* * * * * bash \"$DOCKER_DIR/update.sh\" --cron $marker"
  local existing
  existing="$(crontab -l 2>/dev/null | grep -v "$marker" || true)"
  printf '%s\n%s\n' "$existing" "$cron_line" | crontab -
  log_info "Update cron installed — daemon polls every minute for queued updates."
  log_info "Toggle auto-update on/off from Admin → Updates. Remove with: crontab -e"
}

# ── Success ───────────────────────────────────────────────────────────────────

print_success() {
  local app_url="http://localhost:8000"
  local allowed
  allowed="$(env_get ALLOWED_ORIGINS 2>/dev/null || true)"
  if [[ -n "$allowed" && "$allowed" != "*" ]]; then
    app_url="$allowed"
  fi

  echo ""
  echo "  ╔══════════════════════════════════════════════╗"
  echo "  ║       LogCore OS is running!                 ║"
  echo "  ╚══════════════════════════════════════════════╝"
  echo ""
  echo "  App:           $app_url"
  echo "  Notifications: http://localhost:5680  (ntfy)"
  echo ""
  echo "  First time? Register at $app_url"
  echo "  The first user to register becomes admin."
  echo ""
  echo "  Stop:    docker compose -f docker/docker-compose.yml down"
  echo "  Logs:    docker compose -f docker/docker-compose.yml logs -f app"
  echo "  Backup:  bash docker/backup.sh"
  echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
  parse_flags "$@"
  install_deps
  ensure_docker_group "$@"

  echo ""
  echo "LogCore OS — Launch"
  echo "==================="
  echo ""

  check_prerequisites

  if [[ ! -f "$ENV_FILE" ]]; then
    generate_env
  elif [[ "$FLAG_RECONFIGURE" == "true" ]]; then
    log_warn "Reconfigure mode: docker/.env will be overwritten in 5 seconds."
    log_warn "Press Ctrl+C to abort."
    sleep 5
    generate_env
  else
    log_info "docker/.env exists — skipping setup (use --reconfigure to reset it)."
  fi

  sync_tunnel_token

  # --tunnel-token flag wins over brain/hosting.json
  if [[ -n "$FLAG_TUNNEL_TOKEN" ]]; then
    env_set CLOUDFLARE_TUNNEL_TOKEN "$FLAG_TUNNEL_TOKEN"
    log_info "Cloudflare tunnel token set from --tunnel-token."
  fi

  # Keep DOCKER_GID current (socket GID can vary by host/distro)
  env_set DOCKER_GID "$(stat -c '%g' /var/run/docker.sock 2>/dev/null || echo '999')"

  fix_brain_ownership
  build_frontend
  launch_containers
  wait_for_health
  write_installed_version
  install_update_cron
  print_success
}

main "$@"
