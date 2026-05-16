#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
BACKUP_ROOT=${BACKUP_DIRECTORY:-"$PROJECT_ROOT/backups/sql"}
LABEL=${1:-manual}
TIMESTAMP=$(date -u +"%Y%m%d-%H%M%S")
REQUESTED_ARCHIVE_NAME=${BACKUP_ARCHIVE_NAME:-}
if [ -n "$REQUESTED_ARCHIVE_NAME" ]; then
  case "$REQUESTED_ARCHIVE_NAME" in
    ""|.*|*..*|*[!A-Za-z0-9._-]*)
      echo "BACKUP_ARCHIVE_NAME must be a safe file name" >&2
      exit 64
      ;;
  esac
  case "$REQUESTED_ARCHIVE_NAME" in
    *.tar.gz) ;;
    *)
      echo "BACKUP_ARCHIVE_NAME must end with .tar.gz" >&2
      exit 64
      ;;
  esac
  ARCHIVE_NAME=$REQUESTED_ARCHIVE_NAME
else
  ARCHIVE_NAME="${LABEL}-db-backup-${TIMESTAMP}.tar.gz"
fi
ARCHIVE_PATH="$BACKUP_ROOT/$ARCHIVE_NAME"
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/telegram-private-access-bot-backup.XXXXXX")
DUMP_PATH="$WORK_DIR/database.sql"
MANIFEST_PATH="$WORK_DIR/manifest.json"
RESTORE_PATH="$WORK_DIR/RESTORE.txt"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT HUP INT TERM

: "${DATABASE_URL:?DATABASE_URL is required}"
command -v pg_dump >/dev/null 2>&1 || {
  echo "pg_dump is required" >&2
  exit 1
}
command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required" >&2
  exit 1
}
command -v tar >/dev/null 2>&1 || {
  echo "tar is required" >&2
  exit 1
}

mkdir -p "$BACKUP_ROOT"

pg_dump --no-owner --no-privileges --format=plain --file "$DUMP_PATH" "$DATABASE_URL"

cat >"$MANIFEST_PATH" <<EOF
{
  "created_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "label": "$LABEL",
  "archive_name": "$ARCHIVE_NAME",
  "format": "postgresql-sql-v1",
  "database_url_source": "DATABASE_URL",
  "contains_secrets": false,
  "restore_script": "scripts/restore_db.sh"
}
EOF

python3 - "$MANIFEST_PATH" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
with path.open("r", encoding="utf-8") as handle:
    manifest = json.load(handle)
required = {
    "archive_name",
    "contains_secrets",
    "created_at",
    "database_url_source",
    "format",
    "label",
    "restore_script",
}
missing = sorted(required - manifest.keys())
if missing:
    raise SystemExit(f"manifest.json is missing keys: {', '.join(missing)}")
PY

cat >"$RESTORE_PATH" <<'EOF'
Restore steps
=============

1. Verify the archive: sh scripts/verify_backup.sh /path/to/archive.tar.gz
2. Export a fresh safety copy before restore.
3. Stop the bot workers before importing the dump.
4. Restore with: sh scripts/restore_db.sh /path/to/archive.tar.gz
5. Re-apply migrations and verify subscriptions, tariffs, channels and payments.
EOF

tar -czf "$ARCHIVE_PATH" -C "$WORK_DIR" manifest.json database.sql RESTORE.txt
printf '%s\n' "$ARCHIVE_PATH"
