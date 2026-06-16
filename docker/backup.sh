#!/usr/bin/env bash
# LogCore OS — Backup Script
# Creates a timestamped archive of all user data (Brain files + auth).
#
# Usage:
#   bash docker/backup.sh                    # saves to ./backups/
#   bash docker/backup.sh /path/to/backups   # saves to a custom path
#
# To run automatically, add a cron entry on the host:
#   0 3 * * * /path/to/logcoreos/docker/backup.sh >> /var/log/logcore-backup.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${1:-$REPO_ROOT/backups}"
TIMESTAMP="$(date +%Y-%m-%d_%H-%M-%S)"
ARCHIVE="$BACKUP_DIR/logcore-backup-$TIMESTAMP.tar.gz"

mkdir -p "$BACKUP_DIR"

tar -czf "$ARCHIVE" \
  -C "$REPO_ROOT" \
  brain/ \
  $([ -f "$REPO_ROOT/auth.json" ] && echo "auth.json" || true)

echo "Backup saved: $ARCHIVE"

# Keep only the 30 most recent backups
ls -t "$BACKUP_DIR"/logcore-backup-*.tar.gz 2>/dev/null | tail -n +31 | xargs -r rm --
