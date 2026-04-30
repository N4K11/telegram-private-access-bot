#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BACKUP_SCRIPT="$SCRIPT_DIR/backup_db.sh"
VERIFY_SCRIPT="$SCRIPT_DIR/verify_backup.sh"

if [ $# -lt 1 ]; then
  echo "Usage: $0 /path/to/archive.tar.gz" >&2
  exit 64
fi

ARCHIVE_PATH=$1
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/telegram-private-access-bot-restore.XXXXXX")
DUMP_PATH="$WORK_DIR/database.sql"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT HUP INT TERM

: "${DATABASE_URL:?DATABASE_URL is required}"
command -v psql >/dev/null 2>&1 || {
  echo "psql is required" >&2
  exit 1
}
command -v tar >/dev/null 2>&1 || {
  echo "tar is required" >&2
  exit 1
}

[ -f "$ARCHIVE_PATH" ] || {
  echo "Archive not found: $ARCHIVE_PATH" >&2
  exit 1
}

sh "$VERIFY_SCRIPT" "$ARCHIVE_PATH"
SAFETY_BACKUP=$(sh "$BACKUP_SCRIPT" safety-restore)

tar -xzf "$ARCHIVE_PATH" -C "$WORK_DIR" database.sql
[ -s "$DUMP_PATH" ] || {
  echo "database.sql is missing or empty" >&2
  exit 1
}

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$DUMP_PATH"
printf 'Restore completed. Safety backup: %s\n' "$SAFETY_BACKUP"