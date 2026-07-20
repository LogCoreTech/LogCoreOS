#!/usr/bin/env bash
# LogCore OS — Backup Script
# Creates a timestamped archive of all user data (Brain files + auth).
#
# ⚠️  SECRET-GRADE OUTPUT: the archive contains brain/_system/auth.json (bcrypt
#     password hashes), Finance/simplefin.json (bank access URLs), and any VAPID /
#     Infisical key material. Treat every backup file as sensitive — store it with
#     restrictive permissions and, ideally, encrypted (see below).
#
# Usage:
#   bash docker/backup.sh                    # saves to ./backups/
#   bash docker/backup.sh /path/to/backups   # saves to a custom path
#
# Encryption (opt-in — requires gpg on the host):
#   BACKUP_GPG_RECIPIENT=you@example.com bash docker/backup.sh   # asymmetric (public key)
#   BACKUP_PASSPHRASE='correct horse …'     bash docker/backup.sh # symmetric (passphrase)
#   When either is set the plaintext tarball is removed and only the .gpg file is kept.
#
# Automated (add to host cron):
#   0 3 * * * /path/to/logcoreos/docker/backup.sh >> /var/log/logcore-backup.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${1:-$REPO_ROOT/backups}"
TIMESTAMP="$(date +%Y-%m-%d_%H-%M-%S)"
ARCHIVE="$BACKUP_DIR/logcore-backup-$TIMESTAMP.tar.gz"

mkdir -p "$BACKUP_DIR"
# Backups hold secret-grade data — keep the directory owner-only.
chmod 700 "$BACKUP_DIR" 2>/dev/null || true

# Auth data lives in brain/_system/ — covered by the brain/ backup below
if [ ! -d "$REPO_ROOT/brain" ]; then
  echo "ERROR: brain/ directory not found at $REPO_ROOT/brain — nothing to back up."
  exit 1
fi

# Create archive (brain/_system/auth.json is included automatically)
tar -czf "$ARCHIVE" -C "$REPO_ROOT" brain/
chmod 600 "$ARCHIVE"

# Verify the archive is valid before rotating old backups
if ! tar -tzf "$ARCHIVE" > /dev/null 2>&1; then
  echo "ERROR: Backup verification failed — archive may be corrupt: $ARCHIVE"
  rm -f "$ARCHIVE"
  exit 1
fi

# Optional encryption. When configured, the plaintext tarball is replaced by a .gpg file.
FINAL="$ARCHIVE"
if [ -n "${BACKUP_GPG_RECIPIENT:-}" ] || [ -n "${BACKUP_PASSPHRASE:-}" ]; then
  if ! command -v gpg > /dev/null 2>&1; then
    echo "ERROR: encryption requested but 'gpg' is not installed. Aborting (plaintext removed)."
    rm -f "$ARCHIVE"
    exit 1
  fi
  ENC="$ARCHIVE.gpg"
  if [ -n "${BACKUP_GPG_RECIPIENT:-}" ]; then
    gpg --batch --yes --trust-model always -o "$ENC" -e -r "$BACKUP_GPG_RECIPIENT" "$ARCHIVE"
  else
    printf '%s' "$BACKUP_PASSPHRASE" \
      | gpg --batch --yes --passphrase-fd 0 -o "$ENC" -c "$ARCHIVE"
  fi
  chmod 600 "$ENC"
  rm -f "$ARCHIVE"
  FINAL="$ENC"
  echo "Backup saved, verified, and encrypted: $FINAL"
else
  echo "Backup saved and verified: $FINAL"
  echo "NOTE: this archive is UNENCRYPTED and contains password hashes + bank access URLs."
  echo "      Store it encrypted / access-restricted, or set BACKUP_GPG_RECIPIENT / BACKUP_PASSPHRASE."
fi

# Keep only the 30 most recent backups (plaintext or encrypted)
ls -t "$BACKUP_DIR"/logcore-backup-*.tar.gz "$BACKUP_DIR"/logcore-backup-*.tar.gz.gpg 2>/dev/null \
  | tail -n +31 | xargs -r rm --

echo "Done. Total backups: $(ls "$BACKUP_DIR"/logcore-backup-*.tar.gz "$BACKUP_DIR"/logcore-backup-*.tar.gz.gpg 2>/dev/null | wc -l)"
