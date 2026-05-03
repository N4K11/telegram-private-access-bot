#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SERVICE_NAME=${SERVICE_NAME:-telegram-private-access-bot.service}
VENV_PATH=${VENV_PATH:-"$PROJECT_ROOT/.venv"}

cd "$PROJECT_ROOT"

git pull --ff-only

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
python -m compileall -q app tests alembic
ruff check .
pytest -q -p no:cacheprovider
python -m alembic upgrade head
python -m app.healthcheck
sh "$PROJECT_ROOT/scripts/backup_db.sh" pre-deploy
systemctl restart "$SERVICE_NAME"
systemctl status "$SERVICE_NAME" --no-pager
if [ "${USE_WEBHOOK:-false}" = "true" ]; then
  bash "$PROJECT_ROOT/scripts/smoke_webhook_runtime.sh"
fi
journalctl -u "$SERVICE_NAME" -n 80 --no-pager
