#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SERVICE_NAME=${SERVICE_NAME:-telegram-private-access-bot.service}
VENV_PATH=${VENV_PATH:-"$PROJECT_ROOT/.venv"}
DEPLOY_STAMP=${DEPLOY_STAMP:-$(date -u +"%Y%m%d-%H%M%SZ")}
ROLLBACK_NOTES_DIRECTORY=${ROLLBACK_NOTES_DIRECTORY:-"$PROJECT_ROOT/backups/deploy"}
QUALITY_GATE_SUMMARY_PATH=${QUALITY_GATE_SUMMARY_PATH:-"$ROLLBACK_NOTES_DIRECTORY/quality-gate-$DEPLOY_STAMP.json"}
SMOKE_SUMMARY_PATH=${SMOKE_SUMMARY_PATH:-"$ROLLBACK_NOTES_DIRECTORY/smoke-$DEPLOY_STAMP.json"}

cd "$PROJECT_ROOT"

PREVIOUS_REVISION=$(git rev-parse --short HEAD)
git pull --ff-only
CURRENT_REVISION=$(git rev-parse --short HEAD)

if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  . "$PROJECT_ROOT/.env"
  set +a
fi

if [ -f "$VENV_PATH/bin/activate" ]; then
  . "$VENV_PATH/bin/activate"
fi

python -m pip install --upgrade pip
python -m pip install .[dev]
python -m app.tools.quality_gate --summary-json "$QUALITY_GATE_SUMMARY_PATH"
mkdir -p "$ROLLBACK_NOTES_DIRECTORY"
ROLLBACK_BACKUP_NAME="predeploy-$DEPLOY_STAMP-db-backup.tar.gz"
ROLLBACK_BACKUP_PATH=$(BACKUP_ARCHIVE_NAME="$ROLLBACK_BACKUP_NAME" sh "$PROJECT_ROOT/scripts/backup_db.sh" "predeploy-$DEPLOY_STAMP")
ROLLBACK_NOTES_PATH="$ROLLBACK_NOTES_DIRECTORY/rollback-$DEPLOY_STAMP.txt"
cat >"$ROLLBACK_NOTES_PATH" <<EOF
Deploy stamp: $DEPLOY_STAMP
Service: $SERVICE_NAME
Previous revision: $PREVIOUS_REVISION
Current revision: $CURRENT_REVISION
Quality gate summary: $QUALITY_GATE_SUMMARY_PATH
Rollback backup: $ROLLBACK_BACKUP_PATH
Smoke summary: $SMOKE_SUMMARY_PATH
Rollback steps:
1. Restore DB from backup archive if needed.
2. git checkout $PREVIOUS_REVISION
3. Restart $SERVICE_NAME
4. Re-run webhook smoke and /admin_health, /admin_channel_check
EOF
printf 'Deploy stamp: %s\n' "$DEPLOY_STAMP"
printf 'Quality gate summary: %s\n' "$QUALITY_GATE_SUMMARY_PATH"
printf 'Rollback backup: %s\n' "$ROLLBACK_BACKUP_PATH"
printf 'Smoke summary: %s\n' "$SMOKE_SUMMARY_PATH"
printf 'Rollback notes: %s\n' "$ROLLBACK_NOTES_PATH"
systemctl restart "$SERVICE_NAME"
systemctl status "$SERVICE_NAME" --no-pager
if [ "${USE_WEBHOOK:-false}" = "true" ]; then
  export DEPLOY_STAMP
  export ROLLBACK_BACKUP_PATH
  export SMOKE_SUMMARY_PATH
  bash "$PROJECT_ROOT/scripts/smoke_webhook_runtime.sh"
fi
journalctl -u "$SERVICE_NAME" -n 80 --no-pager
