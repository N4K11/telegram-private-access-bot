from __future__ import annotations

from pathlib import Path

from app.tools.quality_gate import build_quality_gate_steps

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "tests.yml"


def test_ci_workflow_exists_and_runs_core_checks() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert WORKFLOW_PATH.exists() is True
    assert "python -m app.tools.quality_gate --summary-json .tmp/quality-gate.json" in text
    assert "uses: actions/upload-artifact@v4" in text
    assert "if: always()" in text
    assert "name: quality-gate-summary" in text
    assert "path: .tmp/quality-gate.json" in text
    assert "if-no-files-found: error" in text
    assert "python -m compileall ." not in text
    assert "ruff check ." not in text


def test_ci_workflow_runs_repository_sanity_checks() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    step_names = [step.name for step in build_quality_gate_steps()]

    assert "repo_sanity" in step_names
    assert "name: Repository sanity" not in text
    assert "python - <<'PY'" not in text
    assert "test ! -f .env" not in text
