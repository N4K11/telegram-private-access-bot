from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPT_FILES = {
    "BOT_FUTURE_IMPROVEMENTS_CODEX_PROMPTS.md",
    "CODEX_FIX_UI_ENCODING_ADMIN_PROMPT.md",
    "CURRENT_BOT_NEXT_IMPROVEMENTS_ROADMAP.md",
    "UI_MINIMAL_REDESIGN_PROMPT.md",
}
REQUIRED_DOCS = ("README.md", "RUNTIME_MAP.md", "DIAGNOSTICS.md")
REQUIRED_GITIGNORE_PATTERNS = {
    ".env",
    ".venv/",
    "__pycache__/",
    "*.pyc",
    ".pytest_cache/",
    ".ruff_cache/",
    ".tmp/",
    ".vendor/",
    ".tooling/",
    "*.db",
    "data/db.json",
    "backups/*",
    "*.log",
    "logs/",
}
FORBIDDEN_TRACKED_EXACT = {".env", "dev.db", "data/db.json"}
FORBIDDEN_TRACKED_PREFIXES = (
    ".venv/",
    "__pycache__/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".tmp/",
    ".vendor/",
    ".tooling/",
    "backups/",
    "logs/",
)
SCANNED_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".yml",
    ".yaml",
    ".ini",
    ".sh",
    ".service",
    ".html",
    ".svg",
    ".gitignore",
}
SCANNED_NAMES = {"Dockerfile", "Makefile"}
SKIPPED_BINARY_SUFFIXES = {".png", ".zip", ".pyc", ".jpg", ".jpeg", ".ico"}
TOKEN_PATTERN = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{20,}\b")
FORBIDDEN_FRAGMENTS = (
    "Rapira322^",
    "ssh root@193.23.201.190",
)


@dataclass(frozen=True, slots=True)
class RepoSanityIssue:
    code: str
    path: str
    detail: str

    def render(self) -> str:
        return f"{self.code}: {self.path}: {self.detail}"


def collect_repo_sanity_issues(
    *,
    project_root: Path = PROJECT_ROOT,
    tracked_paths: Iterable[str] | None = None,
) -> list[RepoSanityIssue]:
    source_paths = _git_ls_files(project_root) if tracked_paths is None else tracked_paths
    tracked = tuple(_normalize_relative_path(path) for path in source_paths)
    issues: list[RepoSanityIssue] = []
    issues.extend(_check_required_docs(project_root))
    issues.extend(_check_gitignore(project_root))
    issues.extend(_check_tracked_artifacts(tracked))
    issues.extend(_check_tracked_file_contents(project_root, tracked))
    return issues


def run_repo_sanity(
    *,
    project_root: Path = PROJECT_ROOT,
    tracked_paths: Iterable[str] | None = None,
) -> int:
    issues = collect_repo_sanity_issues(
        project_root=project_root,
        tracked_paths=tracked_paths,
    )
    if not issues:
        print("Repository sanity passed.")
        return 0
    print("Repository sanity issues:", file=sys.stderr)
    for issue in issues:
        print(f"  {issue.render()}", file=sys.stderr)
    return 1


def main(_argv: Sequence[str] | None = None) -> int:
    return run_repo_sanity()


def _git_ls_files(project_root: Path) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return tuple(result.stdout.splitlines())


def _check_required_docs(project_root: Path) -> list[RepoSanityIssue]:
    issues: list[RepoSanityIssue] = []
    for relative in REQUIRED_DOCS:
        if not (project_root / relative).is_file():
            issues.append(
                RepoSanityIssue(
                    code="missing_required_doc",
                    path=relative,
                    detail="required project document is missing",
                )
            )
    return issues


def _check_gitignore(project_root: Path) -> list[RepoSanityIssue]:
    path = project_root / ".gitignore"
    if not path.is_file():
        return [
            RepoSanityIssue(
                code="missing_gitignore",
                path=".gitignore",
                detail="required runtime artifact ignore file is missing",
            )
        ]
    lines = {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    missing = sorted(REQUIRED_GITIGNORE_PATTERNS - lines)
    return [
        RepoSanityIssue(
            code="missing_gitignore_pattern",
            path=".gitignore",
            detail=pattern,
        )
        for pattern in missing
    ]


def _check_tracked_artifacts(tracked: Iterable[str]) -> list[RepoSanityIssue]:
    issues: list[RepoSanityIssue] = []
    for relative in tracked:
        if relative == "backups/.gitkeep":
            continue
        if relative in FORBIDDEN_TRACKED_EXACT:
            issues.append(
                RepoSanityIssue(
                    code="tracked_runtime_artifact",
                    path=relative,
                    detail="runtime artifact must not be tracked",
                )
            )
        if relative.endswith(".pyc") or relative.endswith(".log"):
            issues.append(
                RepoSanityIssue(
                    code="tracked_runtime_artifact",
                    path=relative,
                    detail="compiled/log artifacts must not be tracked",
                )
            )
        if any(relative.startswith(prefix) for prefix in FORBIDDEN_TRACKED_PREFIXES):
            issues.append(
                RepoSanityIssue(
                    code="tracked_runtime_artifact",
                    path=relative,
                    detail="ignored runtime/cache directory must not be tracked",
                )
            )
    return issues


def _check_tracked_file_contents(
    project_root: Path,
    tracked: Iterable[str],
) -> list[RepoSanityIssue]:
    issues: list[RepoSanityIssue] = []
    for relative in tracked:
        path = project_root / relative
        if not path.is_file() or path.suffix.lower() in SKIPPED_BINARY_SUFFIXES:
            continue
        data = path.read_bytes()
        if path.suffix == ".sh" and b"\r\n" in data:
            issues.append(
                RepoSanityIssue(
                    code="crlf_shell_script",
                    path=relative,
                    detail="shell scripts must use LF line endings",
                )
            )
        if not _should_scan_text(path, relative):
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if TOKEN_PATTERN.search(text):
            issues.append(
                RepoSanityIssue(
                    code="token_like_pattern",
                    path=relative,
                    detail="token-like pattern detected",
                )
            )
        for fragment in FORBIDDEN_FRAGMENTS:
            if fragment in text:
                issues.append(
                    RepoSanityIssue(
                        code="forbidden_secret_fragment",
                        path=relative,
                        detail=fragment,
                    )
                )
    return issues


def _should_scan_text(path: Path, relative: str) -> bool:
    if path.name in PROMPT_FILES:
        return False
    if relative.startswith("tests/"):
        return False
    return (
        path.suffix.lower() in SCANNED_SUFFIXES
        or path.name in SCANNED_NAMES
        or relative == ".gitignore"
    )


def _normalize_relative_path(path: str) -> str:
    return path.replace("\\", "/")


if __name__ == "__main__":
    raise SystemExit(main())
