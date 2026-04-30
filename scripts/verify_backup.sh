#!/bin/sh
set -eu

if [ $# -lt 1 ]; then
  echo "Usage: $0 /path/to/archive.tar.gz" >&2
  exit 64
fi

ARCHIVE_PATH=$1
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/telegram-private-access-bot-verify.XXXXXX")
MANIFEST_PATH="$WORK_DIR/manifest.json"
DUMP_PATH="$WORK_DIR/database.sql"
RESTORE_PATH="$WORK_DIR/RESTORE.txt"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT HUP INT TERM

[ -f "$ARCHIVE_PATH" ] || {
  echo "Archive not found: $ARCHIVE_PATH" >&2
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

tar -xzf "$ARCHIVE_PATH" -C "$WORK_DIR" manifest.json database.sql RESTORE.txt

[ -s "$DUMP_PATH" ] || {
  echo "database.sql is missing or empty" >&2
  exit 1
}
[ -s "$RESTORE_PATH" ] || {
  echo "RESTORE.txt is missing or empty" >&2
  exit 1
}

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
if manifest["format"] != "postgresql-sql-v1":
    raise SystemExit("unsupported backup format")
PY

printf '%s\n' "Backup archive looks valid: $ARCHIVE_PATH"