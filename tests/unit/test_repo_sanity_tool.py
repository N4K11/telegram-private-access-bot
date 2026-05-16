from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.tools.repo_sanity import (
    PROJECT_ROOT,
    REQUIRED_DOCS,
    REQUIRED_GITIGNORE_PATTERNS,
    collect_repo_sanity_issues,
    run_repo_sanity,
)


def _workspace_tmp() -> Path:
    path = PROJECT_ROOT / ".testdata" / f"repo-sanity-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_required_project_files(project_root: Path) -> None:
    for relative in REQUIRED_DOCS:
        path = project_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {path.stem}\n", encoding="utf-8")
    (project_root / ".gitignore").write_text(
        "\n".join(sorted(REQUIRED_GITIGNORE_PATTERNS)) + "\n",
        encoding="utf-8",
    )


def test_collect_repo_sanity_issues_accepts_clean_tracked_repo() -> None:
    project_root = _workspace_tmp()
    _write_required_project_files(project_root)
    (project_root / "scripts").mkdir()
    (project_root / "scripts" / "deploy.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
    (project_root / "app").mkdir()
    (project_root / "app" / "main.py").write_text("print('ok')\n", encoding="utf-8")

    issues = collect_repo_sanity_issues(
        project_root=project_root,
        tracked_paths=[
            ".gitignore",
            "README.md",
            "RUNTIME_MAP.md",
            "DIAGNOSTICS.md",
            "scripts/deploy.sh",
            "app/main.py",
        ],
    )

    assert issues == []


def test_collect_repo_sanity_issues_reports_release_blockers() -> None:
    project_root = _workspace_tmp()
    _write_required_project_files(project_root)
    (project_root / ".gitignore").write_text(".env\n", encoding="utf-8")
    (project_root / ".env").write_text("BOT_TOKEN=placeholder\n", encoding="utf-8")
    (project_root / "scripts").mkdir()
    (project_root / "scripts" / "deploy.sh").write_bytes(b"#!/bin/sh\r\nexit 0\r\n")
    (project_root / "app").mkdir()
    token_like_value = "123456789:" + ("A" * 24)
    (project_root / "app" / "main.py").write_text(
        f"TOKEN = {token_like_value!r}\n",
        encoding="utf-8",
    )

    issues = collect_repo_sanity_issues(
        project_root=project_root,
        tracked_paths=[".env", "scripts/deploy.sh", "app/main.py"],
    )
    codes = {issue.code for issue in issues}

    assert "tracked_runtime_artifact" in codes
    assert "missing_gitignore_pattern" in codes
    assert "crlf_shell_script" in codes
    assert "token_like_pattern" in codes
    assert any(
        issue.code == "missing_gitignore_pattern" and issue.detail == "data/db.json"
        for issue in issues
    )


def test_collect_repo_sanity_issues_skips_test_fixture_secret_patterns() -> None:
    project_root = _workspace_tmp()
    _write_required_project_files(project_root)
    (project_root / "tests" / "unit").mkdir(parents=True)
    token_like_value = "123456789:" + ("B" * 24)
    (project_root / "tests" / "unit" / "test_fixture.py").write_text(
        f"TOKEN_FIXTURE = {token_like_value!r}\n",
        encoding="utf-8",
    )

    issues = collect_repo_sanity_issues(
        project_root=project_root,
        tracked_paths=[
            ".gitignore",
            "README.md",
            "RUNTIME_MAP.md",
            "DIAGNOSTICS.md",
            "tests/unit/test_fixture.py",
        ],
    )

    assert issues == []


def test_run_repo_sanity_prints_pass_output(capsys) -> None:
    project_root = _workspace_tmp()
    _write_required_project_files(project_root)

    result = run_repo_sanity(
        project_root=project_root,
        tracked_paths=[".gitignore", "README.md", "RUNTIME_MAP.md", "DIAGNOSTICS.md"],
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "Repository sanity passed." in captured.out
    assert captured.err == ""


def test_run_repo_sanity_prints_failure_output(capsys) -> None:
    project_root = _workspace_tmp()
    (project_root / ".gitignore").write_text("", encoding="utf-8")

    result = run_repo_sanity(project_root=project_root, tracked_paths=[])

    captured = capsys.readouterr()
    assert result == 1
    assert "Repository sanity issues:" in captured.err
    assert "missing_required_doc" in captured.err
