from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = PROJECT_ROOT / "scripts" / "deploy.sh"


def test_deploy_script_exists_and_uses_strict_mode() -> None:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    content = DEPLOY_SCRIPT.read_bytes()

    assert DEPLOY_SCRIPT.exists() is True
    assert content.startswith(b"#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text


def test_deploy_script_runs_checks_before_restart_and_backs_up_first() -> None:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    quality_gate_pos = text.index(
        'python -m app.tools.quality_gate --summary-json "$QUALITY_GATE_SUMMARY_PATH"'
    )
    backup_command = (
        'ROLLBACK_BACKUP_PATH=$(BACKUP_ARCHIVE_NAME="$ROLLBACK_BACKUP_NAME" '
        'sh "$PROJECT_ROOT/scripts/backup_db.sh" "predeploy-$DEPLOY_STAMP")'
    )
    backup_pos = text.index(backup_command)
    restart_pos = text.index('systemctl restart "$SERVICE_NAME"')

    assert quality_gate_pos < backup_pos < restart_pos
    assert "python -m compileall ." not in text
    assert "ruff check ." not in text


def test_deploy_script_runs_webhook_smoke_after_restart_when_enabled() -> None:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    restart_pos = text.index('systemctl restart "$SERVICE_NAME"')
    status_pos = text.index('systemctl status "$SERVICE_NAME" --no-pager')
    smoke_guard_pos = text.index('if [ "${USE_WEBHOOK:-false}" = "true" ]; then')
    smoke_pos = text.index('  bash "$PROJECT_ROOT/scripts/smoke_webhook_runtime.sh"')

    assert restart_pos < status_pos < smoke_guard_pos < smoke_pos


def test_deploy_script_creates_deterministic_deploy_stamp_and_rollback_notes() -> None:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'DEPLOY_STAMP=${DEPLOY_STAMP:-$(date -u +"%Y%m%d-%H%M%SZ")}' in text
    assert (
        'ROLLBACK_NOTES_DIRECTORY=${ROLLBACK_NOTES_DIRECTORY:-"$PROJECT_ROOT/backups/deploy"}'
        in text
    )
    assert 'PREVIOUS_REVISION=$(git rev-parse --short HEAD)' in text
    assert 'CURRENT_REVISION=$(git rev-parse --short HEAD)' in text
    quality_gate_summary_default = (
        'QUALITY_GATE_SUMMARY_PATH=${QUALITY_GATE_SUMMARY_PATH:-'
        '"$ROLLBACK_NOTES_DIRECTORY/quality-gate-$DEPLOY_STAMP.json"}'
    )
    smoke_summary_default = (
        'SMOKE_SUMMARY_PATH=${SMOKE_SUMMARY_PATH:-'
        '"$ROLLBACK_NOTES_DIRECTORY/smoke-$DEPLOY_STAMP.json"}'
    )
    assert quality_gate_summary_default in text
    assert smoke_summary_default in text
    assert 'Quality gate summary: $QUALITY_GATE_SUMMARY_PATH' in text
    assert 'Smoke summary: $SMOKE_SUMMARY_PATH' in text
    assert 'ROLLBACK_BACKUP_NAME="predeploy-$DEPLOY_STAMP-db-backup.tar.gz"' in text
    assert (
        'BACKUP_ARCHIVE_NAME="$ROLLBACK_BACKUP_NAME" sh "$PROJECT_ROOT/scripts/backup_db.sh"'
        in text
    )
    assert 'ROLLBACK_NOTES_PATH="$ROLLBACK_NOTES_DIRECTORY/rollback-$DEPLOY_STAMP.txt"' in text
    assert 'printf \'Deploy stamp: %s\\n\' "$DEPLOY_STAMP"' in text
    assert 'printf \'Quality gate summary: %s\\n\' "$QUALITY_GATE_SUMMARY_PATH"' in text
    assert 'printf \'Rollback backup: %s\\n\' "$ROLLBACK_BACKUP_PATH"' in text
    assert 'printf \'Smoke summary: %s\\n\' "$SMOKE_SUMMARY_PATH"' in text
    assert 'export DEPLOY_STAMP' in text
    assert 'export ROLLBACK_BACKUP_PATH' in text
    assert 'export SMOKE_SUMMARY_PATH' in text


def test_deploy_script_has_no_secrets_or_windows_paths() -> None:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    forbidden_literals = [
        "AAEjnqo",
        "Rapira",
        "BOT_TOKEN=",
        "CRYPTO_PAY_TOKEN=",
        "D:\\",
        "C:\\",
    ]
    for literal in forbidden_literals:
        assert literal not in text
