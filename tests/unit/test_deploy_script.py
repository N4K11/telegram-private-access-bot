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

    compile_pos = text.index("python -m compileall -q app tests alembic")
    lint_pos = text.index("ruff check .")
    pytest_pos = text.index("pytest -q -p no:cacheprovider")
    alembic_pos = text.index("python -m alembic upgrade head")
    backup_pos = text.index('sh "$PROJECT_ROOT/scripts/backup_db.sh" pre-deploy')
    restart_pos = text.index('systemctl restart "$SERVICE_NAME"')

    assert compile_pos < restart_pos
    assert lint_pos < restart_pos
    assert pytest_pos < restart_pos
    assert alembic_pos < restart_pos
    assert backup_pos < restart_pos


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
