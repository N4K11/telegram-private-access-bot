from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, TextIO

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPILEALL_PATHS = ("app", "tests", "alembic", "scripts")
RUFF_PATHS = ("app", "tests", "alembic")


@dataclass(frozen=True, slots=True)
class QualityGateStep:
    name: str
    command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QualityGateStepResult:
    name: str
    returncode: int
    duration_ms: int

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def build_quality_gate_steps(
    *,
    project_root: Path = PROJECT_ROOT,
    include_tests: bool = True,
    include_db: bool = True,
    include_healthcheck: bool = True,
    include_text_scan: bool = True,
    include_repo_sanity: bool = True,
) -> tuple[QualityGateStep, ...]:
    steps: list[QualityGateStep] = [
        QualityGateStep(
            name="compileall",
            command=(sys.executable, "-m", "compileall", "-q", *COMPILEALL_PATHS),
        ),
        QualityGateStep(
            name="ruff",
            command=(*_resolve_ruff_command(project_root), "check", *RUFF_PATHS),
        ),
    ]
    if include_repo_sanity:
        steps.append(
            QualityGateStep(
                name="repo_sanity",
                command=(sys.executable, "-m", "app.tools.repo_sanity"),
            )
        )
    if include_tests:
        steps.append(
            QualityGateStep(
                name="pytest",
                command=(sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"),
            )
        )
    if include_db:
        steps.append(
            QualityGateStep(
                name="alembic",
                command=(sys.executable, "-m", "alembic", "upgrade", "head"),
            )
        )
    if include_healthcheck:
        steps.append(
            QualityGateStep(
                name="healthcheck",
                command=(sys.executable, "-m", "app.healthcheck"),
            )
        )
    if include_text_scan:
        steps.append(
            QualityGateStep(
                name="scan_texts",
                command=(sys.executable, "-m", "app.tools.scan_texts"),
            )
        )
    return tuple(steps)


def quality_gate_environment(
    *,
    project_root: Path = PROJECT_ROOT,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    env = dict(base_env or os.environ)
    tooling_path = project_root / ".tooling"
    if tooling_path.exists():
        existing = env.get("PYTHONPATH", "")
        entries = [item for item in existing.split(os.pathsep) if item]
        tooling_value = str(tooling_path)
        if tooling_value not in entries:
            env["PYTHONPATH"] = os.pathsep.join([tooling_value, *entries])
    return env


def run_quality_gate(
    steps: Iterable[QualityGateStep],
    *,
    project_root: Path = PROJECT_ROOT,
    env: dict[str, str] | None = None,
    runner: Callable[..., Any] = subprocess.run,
    clock: Callable[[], float] = perf_counter,
    output: TextIO = sys.stdout,
    summary_json_path: Path | None = None,
) -> int:
    resolved_env = env or quality_gate_environment(project_root=project_root)
    results: list[QualityGateStepResult] = []
    for step in steps:
        print(f"==> {step.name}: {' '.join(step.command)}", file=output, flush=True)
        started_at = clock()
        result = runner(step.command, cwd=project_root, env=resolved_env, check=False)
        duration_ms = round((clock() - started_at) * 1000)
        step_result = QualityGateStepResult(
            name=step.name,
            returncode=int(result.returncode),
            duration_ms=max(0, duration_ms),
        )
        results.append(step_result)
        print(
            f"<== {step.name}: {_format_step_status(step_result)}",
            file=output,
            flush=True,
        )
        if not step_result.ok:
            _finish_quality_gate(results, summary_json_path=summary_json_path, output=output)
            return step_result.returncode
    _finish_quality_gate(results, summary_json_path=summary_json_path, output=output)
    return 0


def format_quality_gate_summary(results: Sequence[QualityGateStepResult]) -> str:
    total_ms = sum(item.duration_ms for item in results)
    failed = [item for item in results if not item.ok]
    status = "FAIL" if failed else "PASS"
    lines = ["Quality gate summary:"]
    for item in results:
        lines.append(f"- {item.name}: {_format_step_status(item)}")
    lines.append(f"Quality gate result: {status} ({total_ms} ms)")
    return "\n".join(lines)


def quality_gate_summary_payload(
    results: Sequence[QualityGateStepResult],
) -> dict[str, object]:
    total_ms = sum(item.duration_ms for item in results)
    failed = [item for item in results if not item.ok]
    return {
        "ok": not failed,
        "status": "fail" if failed else "pass",
        "total_duration_ms": total_ms,
        "failed_step": failed[0].name if failed else None,
        "steps": [
            {
                "name": item.name,
                "ok": item.ok,
                "returncode": item.returncode,
                "duration_ms": item.duration_ms,
            }
            for item in results
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the repository quality gate on source paths only. "
            "This intentionally avoids root-level compileall over local caches."
        )
    )
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest.")
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip Alembic upgrade and app.healthcheck.",
    )
    parser.add_argument(
        "--skip-repo-sanity",
        action="store_true",
        help="Skip tracked-file repository sanity checks.",
    )
    parser.add_argument("--skip-text-scan", action="store_true", help="Skip mojibake scan.")
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Write a machine-readable quality gate summary to this JSON file.",
    )
    args = parser.parse_args(argv)

    steps = build_quality_gate_steps(
        include_tests=not args.skip_tests,
        include_db=not args.skip_db,
        include_healthcheck=not args.skip_db,
        include_text_scan=not args.skip_text_scan,
        include_repo_sanity=not args.skip_repo_sanity,
    )
    return run_quality_gate(steps, summary_json_path=args.summary_json)


def _resolve_ruff_command(project_root: Path) -> tuple[str, ...]:
    executable = shutil.which("ruff")
    if executable:
        return (executable,)
    local_candidates = (
        project_root / ".rufftool" / "Scripts" / "ruff.exe",
        project_root / ".rufftool" / "bin" / "ruff",
    )
    for candidate in local_candidates:
        if candidate.exists():
            return (str(candidate),)
    return (sys.executable, "-m", "ruff")


def _format_step_status(result: QualityGateStepResult) -> str:
    status = "PASS" if result.ok else f"FAIL code={result.returncode}"
    return f"{status} ({result.duration_ms} ms)"


def _finish_quality_gate(
    results: Sequence[QualityGateStepResult],
    *,
    summary_json_path: Path | None,
    output: TextIO,
) -> None:
    print(format_quality_gate_summary(results), file=output, flush=True)
    if summary_json_path is not None:
        _write_quality_gate_summary_json(summary_json_path, results)
        print(
            f"Quality gate summary JSON: {summary_json_path}",
            file=output,
            flush=True,
        )


def _write_quality_gate_summary_json(
    summary_json_path: Path,
    results: Sequence[QualityGateStepResult],
) -> None:
    summary_json_path.parent.mkdir(parents=True, exist_ok=True)
    summary_json_path.write_text(
        json.dumps(
            quality_gate_summary_payload(results),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
