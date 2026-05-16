from __future__ import annotations

import json
import os
import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.tools.quality_gate import (
    COMPILEALL_PATHS,
    PROJECT_ROOT,
    RUFF_PATHS,
    QualityGateStepResult,
    build_quality_gate_steps,
    quality_gate_environment,
    quality_gate_summary_payload,
    run_quality_gate,
)


def _step_commands() -> dict[str, tuple[str, ...]]:
    return {step.name: step.command for step in build_quality_gate_steps()}


def _workspace_tmp() -> Path:
    path = PROJECT_ROOT / ".testdata" / f"quality-gate-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_quality_gate_uses_scoped_compileall_paths() -> None:
    commands = _step_commands()

    assert commands["compileall"] == (
        sys.executable,
        "-m",
        "compileall",
        "-q",
        *COMPILEALL_PATHS,
    )
    assert "." not in commands["compileall"]
    assert ".vendor" not in commands["compileall"]
    assert ".tooling" not in commands["compileall"]


def test_quality_gate_uses_project_scoped_ruff_paths() -> None:
    commands = _step_commands()

    assert commands["ruff"][-len(RUFF_PATHS) :] == RUFF_PATHS
    assert "." not in commands["ruff"]


def test_quality_gate_can_skip_slow_or_runtime_dependent_steps() -> None:
    steps = build_quality_gate_steps(
        include_tests=False,
        include_db=False,
        include_healthcheck=False,
        include_text_scan=False,
    )

    assert [step.name for step in steps] == ["compileall", "ruff", "repo_sanity"]


def test_quality_gate_can_skip_repo_sanity_for_narrow_debug_runs() -> None:
    steps = build_quality_gate_steps(
        include_tests=False,
        include_db=False,
        include_healthcheck=False,
        include_text_scan=False,
        include_repo_sanity=False,
    )

    assert [step.name for step in steps] == ["compileall", "ruff"]


def test_quality_gate_environment_prepends_local_tooling() -> None:
    project_root = _workspace_tmp()
    tooling = project_root / ".tooling"
    tooling.mkdir()

    env = quality_gate_environment(
        project_root=project_root,
        base_env={"PYTHONPATH": os.pathsep.join(["existing", "other"])},
    )

    assert env["PYTHONPATH"].split(os.pathsep) == [str(tooling), "existing", "other"]


def test_quality_gate_prints_timed_summary() -> None:
    calls: list[tuple[str, ...]] = []
    clock_values = iter([10.0, 10.125, 20.0, 20.050, 30.0, 30.025])
    output = StringIO()
    steps = build_quality_gate_steps(
        include_tests=False,
        include_db=False,
        include_healthcheck=False,
        include_text_scan=False,
    )

    def fake_runner(command, **kwargs):
        calls.append(tuple(command))
        return SimpleNamespace(returncode=0)

    result = run_quality_gate(
        steps,
        env={},
        runner=fake_runner,
        clock=lambda: next(clock_values),
        output=output,
    )

    text = output.getvalue()
    assert result == 0
    assert calls == [step.command for step in steps]
    assert "<== compileall: PASS (125 ms)" in text
    assert "<== ruff: PASS (50 ms)" in text
    assert "<== repo_sanity: PASS (25 ms)" in text
    assert "Quality gate summary:" in text
    assert "Quality gate result: PASS (200 ms)" in text


def test_quality_gate_stops_and_summarizes_on_failure() -> None:
    clock_values = iter([1.0, 1.025])
    output = StringIO()
    steps = (build_quality_gate_steps(include_tests=False)[0],)

    def fake_runner(command, **kwargs):
        return SimpleNamespace(returncode=7)

    result = run_quality_gate(
        steps,
        env={},
        runner=fake_runner,
        clock=lambda: next(clock_values),
        output=output,
    )

    text = output.getvalue()
    assert result == 7
    assert "<== compileall: FAIL code=7 (25 ms)" in text
    assert "Quality gate result: FAIL (25 ms)" in text


def test_quality_gate_writes_summary_json() -> None:
    project_root = _workspace_tmp()
    summary_path = project_root / "reports" / "quality-gate.json"
    clock_values = iter([3.0, 3.010])
    output = StringIO()
    steps = (build_quality_gate_steps(include_tests=False)[0],)

    def fake_runner(command, **kwargs):
        return SimpleNamespace(returncode=0)

    result = run_quality_gate(
        steps,
        project_root=project_root,
        env={},
        runner=fake_runner,
        clock=lambda: next(clock_values),
        output=output,
        summary_json_path=summary_path,
    )

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert result == 0
    assert payload == {
        "failed_step": None,
        "ok": True,
        "status": "pass",
        "steps": [
            {
                "duration_ms": 10,
                "name": "compileall",
                "ok": True,
                "returncode": 0,
            }
        ],
        "total_duration_ms": 10,
    }
    assert f"Quality gate summary JSON: {summary_path}" in output.getvalue()


def test_quality_gate_summary_payload_marks_failed_step() -> None:
    steps = [
        QualityGateStepResult(name="compileall", returncode=0, duration_ms=5),
        QualityGateStepResult(name="ruff", returncode=3, duration_ms=7),
    ]

    payload = quality_gate_summary_payload(steps)

    assert payload["ok"] is False
    assert payload["status"] == "fail"
    assert payload["failed_step"] == "ruff"
    assert payload["total_duration_ms"] == 12
