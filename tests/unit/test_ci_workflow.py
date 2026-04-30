from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "tests.yml"


def test_ci_workflow_exists_and_runs_core_checks() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert WORKFLOW_PATH.exists() is True
    assert "python -m compileall -q app tests alembic" in text
    assert "ruff check ." in text
    assert "pytest -q -p no:cacheprovider" in text
    assert "python -m alembic upgrade head" in text


def test_ci_workflow_runs_repository_sanity_checks() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "test ! -f .env" in text
    assert "test ! -f data/db.json" in text
    assert "test -f README.md" in text
    assert "test -f RUNTIME_MAP.md" in text
    assert "test -f DIAGNOSTICS.md" in text
    assert "CRLF detected in shell script" in text
    assert "Token-like pattern detected in:" in text
