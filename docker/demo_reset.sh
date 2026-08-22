#!/usr/bin/env bash
# LogCore OS — Demo Instance Nightly Reset
#
# For a PUBLIC DEMO instance only (e.g. app.logcoretech.com) — wipes every
# non-admin user's Brain folder and auth.json entry so each day starts
# clean. Never touches admin accounts or the shared household/team pool
# folders. Does nothing destructive on a personal/self-hosted install; only
# run this where "anyone can register and their data resets nightly" is
# the actual intended behavior.
#
# Usage:
#   bash docker/demo_reset.sh
#
# Automated (add to the DEMO HOST's cron, not a personal instance):
#   0 3 * * * cd /path/to/logcoreos && bash docker/demo_reset.sh >> /var/log/logcore-demo-reset.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker compose -f "$SCRIPT_DIR/docker-compose.yml" exec -T app python3 demo_reset.py
