#!/usr/bin/env bash
# LogCore OS — Launch Script
# Builds the frontend, configures the environment, and starts the Docker stack.
#
# Usage:
#   bash launch.sh               # first-time setup or normal restart
#   bash launch.sh --reconfigure # re-run setup even if docker/.env already exists
#   bash launch.sh --skip-build  # skip npm build (requires app/frontend/dist/ to exist)
#
# Requirements: Docker (with Compose plugin v2), Node.js 20+, curl

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
DOCKER_DIR="$REPO_ROOT/docker"
ENV_FILE="$DOCKER_DIR/.env"
ENV_EXAMPLE="$DOCKER_DIR/.env.example"
FRONTEND_DIR="$REPO_ROOT/app/frontend"
DIST_DIR="$FRONTEND_DIR/dist"
HEALTH_URL="http://localhost:8000/api/v1/health"
HEALTH_TIMEOUT=90
HEALTH_INTERVAL=3

FLAG_RECONFIGURE=false
FLAG_SKIP_BUILD=false

# ── Flags ─────────────────────────────────────────────────────────────────────

parse_flags() {
  for arg in "$@"; do
    case "$arg" in
      --reconfigure) FLAG_RECONFIGURE=true ;;
      --skip-build)  FLAG_SKIP_BUILD=true  ;;
      *)
        echo "ERROR: Unknown flag: $arg"
        echo "Usage: bash launch.sh [--reconfigure] [--skip-build]"
        exit 1
        ;;
    esac
  done
}

# ── Logging ───────────────────────────────────────────────────────────────────

log_step() { echo "==> $1"; }
log_info()  { echo "    $1"; }
log_warn()  { echo "    WARNING: $1"; }
die()       { echo "    ERROR: $1"; exit 1; }

# ── Prerequisites ─────────────────────────────────────────────────────────────

check_prerequisites() {
  log_step "Checking prerequisites"

  if ! command -v docker &>/dev/null; then
    die "Docker is not installed.
    Install it from: https://docs.docker.com/engine/install/
    Then re-run this script."
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
  env_set SECRET_KEY    "$secret_key"
  env_set ALLOWED_ORIGINS "*"
  env_set COOKIE_SECURE  "false"
  env_set TRUST_PROXY_HEADERS "false"

  log_info "docker/.env created with a generated SECRET_KEY."
  log_info "After first login, go to Admin → AI Settings to add your API key."
  log_info "Go to Admin → Hosting to enable HTTPS/tunnel mode."
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

launch_containers() {
  log_step "Starting Docker containers"
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

  build_frontend
  launch_containers
  wait_for_health
  print_success
}

main "$@"
